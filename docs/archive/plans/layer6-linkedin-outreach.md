# Layer 6: LinkedIn Outreach Generation Requirements

**Created**: 2025-11-27
**Status**: Documentation
**Priority**: Critical for Phase 2 outreach implementation

---

## Overview

Layer 6 generates hyper-personalized LinkedIn outreach messages that respect LinkedIn's character limits while including mandatory personalization elements and Taimoor Alam's signature.

---

## LinkedIn Character Limits (CRITICAL)

All LinkedIn message types have hard character limits enforced by the platform:

| Message Type | Character Limit | Enforced By | Notes |
|--------------|-----------------|------------|-------|
| **Connection Request** | 300 characters | LinkedIn API | Message rejected if over limit |
| **InMail Body** | 1900 characters | LinkedIn API | Message truncated if over limit |
| **InMail Subject** | 200 characters | LinkedIn API | Subject line truncated |
| **Direct Message** | No hard limit | N/A | Best practice: 500-1000 chars |

---

## Mandatory Signature

**Exact Format Required**:
```
Best. Taimoor Alam
```

**Specification**:
- Word "Best" with period: `Best.` (not "Best," or "Best")
- Space followed by full name: ` Taimoor Alam`
- Case-sensitive: Must be capitalized as shown
- No variations: Cannot use "Best regards," "Warm regards," etc.

**Placement Rules**:

| Message Type | Signature Placement |
|--------------|-------------------|
| Connection Request | After Calendly URL, on separate line |
| InMail | At end of message body, after Calendly URL |
| Direct Message | At end of message |

**Implementation**:
- Signature is MANDATORY - every message must include it
- Signature counts toward character limit
- Do not prompt LLM to generate signature - always append it
- Verify signature presence in validation step

---

## Calendly URL Integration

**Environment Configuration**:
```python
# In .env
CALENDLY_URL=https://calendly.com/taimooralam/30min
```

**URL Handling**:
- Always include full URL (not shortened)
- URL counts toward character limit
- If `CALENDLY_URL` not configured, use fallback or fail validation
- Never replace URL with placeholder in generated message

**Placement Rules**:

| Message Type | Placement |
|--------------|-----------|
| Connection Request | Before signature (same line or new line) |
| InMail | In call-to-action paragraph, before signature |
| Email (Layer 5) | In CTA section (not required for Layer 6) |

---

## Message Templates & Character Budgets

### Connection Request (300 char hard limit)

**Template Structure**:
```
Hi {FirstName}, [Hook]. [Value]. Book time: {CalendlyURL}. Best. Taimoor Alam
```

**Character Budget Breakdown**:
```
"Hi John, " = 9 chars
[pain point hook] = 80-100 chars
[value proposition] = 50-70 chars
"Book time: " = 11 chars
{CalendlyURL} = 40-50 chars (e.g., https://calendly.com/taimooralam/30min)
"Best. Taimoor Alam" = 19 chars
─────────────────────
Total target: 209-259 chars (41-91 char buffer for variation)
```

**Example (Actual Character Count)**:
```
Hi Sarah, I saw your Product Manager role at Stripe and your work on payment latency optimization. I've reduced P99 latency by 300ms at Scale. Let's connect: https://calendly.com/taimooralam/30min Best. Taimoor Alam
```
Character count: 256 (within 300 limit)

**Content Guidelines**:
- Greeting: "Hi {FirstName}," (always)
- Hook: Reference specific pain point from Layer 2
- Value: 1-2 word value proposition (use STAR mapping when available)
- CTA: "Book time: " followed by Calendly URL
- Signature: "Best. Taimoor Alam" (always)
- No line breaks (single paragraph)
- Professional but warm tone

### InMail Messages (1900 char body limit)

**Template Structure**:
```
Subject: {Role} - {PainPoint} Solution [Max 200 chars]

Hi {FirstName},

[Paragraph 1: Hook - 150-200 chars]
Reference specific pain point or achievement with context.

[Paragraph 2: Value - 400-500 chars]
Map candidate's relevant experience to their needs. Include 1-2 STAR examples if available.

[Paragraph 3: Call-to-action - 150-200 chars]
Specific meeting purpose + Calendly link + next steps.

Best. Taimoor Alam
{CalendlyURL}
```

**Character Budget Breakdown**:
```
Subject line: ~50 chars (well under 200 limit)
Greeting: ~20 chars
Paragraph 1 (hook): ~180 chars
Paragraph 2 (value): ~450 chars
Paragraph 3 (CTA): ~180 chars
Signature + URL: ~70 chars
─────────────────────
Total target: ~950 chars (950 char buffer for expansion to 1900)
```

**Example Structure**:
```
Subject: Senior Backend Engineer - Database Performance Solution

Hi Sarah,

I noticed Stripe's database query latency has been a recurring challenge for your platform team. Your work scaling payment processing caught my attention.

I spent the last 2 years optimizing database performance at Scale, reducing P99 query latency from 2.5s to 180ms while handling 10x traffic growth. I implemented connection pooling, query optimization, and caching strategies that improved platform stability. I'd love to discuss how these approaches could help Stripe's backend infrastructure.

Let's explore how we can collaborate. I'm available for a brief call: https://calendly.com/taimooralam/30min

Best. Taimoor Alam
https://calendly.com/taimooralam/30min
```

**Content Guidelines**:
- Subject: Concise value proposition, max 200 chars
- Hook paragraph: Reference specific pain point or achievement
- Value paragraph: Include 2-3 STAR examples mapped to their pain points
- CTA paragraph: Clear meeting purpose and Calendly link
- Signature: "Best. Taimoor Alam" (always)
- Professional but conversational tone
- 3-4 paragraphs (not a wall of text)

---

## Personalization Tokens

All messages use dynamic tokens populated from earlier pipeline layers:

| Token | Source | Example | Required? |
|-------|--------|---------|-----------|
| `{FirstName}` | Layer 5 (People Mapper) | "Sarah" | YES |
| `{Role}` | Job posting | "Senior Backend Engineer" | YES |
| `{Company}` | Job posting | "Stripe" | YES |
| `{PainPoint}` | Layer 2 (Pain Point Miner) | "Database query latency" | YES |
| `{Value}` | Layer 4 (Opportunity Mapper) or STAR | "Reduced latency by 300ms" | For connection requests |
| `{STAR}` | Layer 2.5 (optional) | Full STAR story | For InMail when available |
| `{CalendlyURL}` | Environment variable | https://calendly.com/... | YES |

**Token Replacement Rules**:
- Replace ALL tokens before sending message
- Validation step must verify NO `{Token}` placeholders remain
- If token unavailable, use generic fallback:
  - `{FirstName}` → "there"
  - `{Value}` → "my relevant experience"
  - `{PainPoint}` → "your hiring challenges"

---

## Message Generation Flow

### Step 1: LLM Prompt Engineering

**System Prompt** (for outreach generator):
```
You are a LinkedIn outreach specialist generating highly personalized messages.

CONSTRAINTS:
1. Character limit STRICT: {limit} characters for this message type
2. Include mandatory signature: "Best. Taimoor Alam"
3. Include Calendly URL: {calendly_url}
4. Reference pain point: {pain_point}
5. Professional but warm tone

REQUIRED FORMAT:
[Message body with all required elements]

FINAL CHECK:
- Count characters: Message must be ≤ {limit} chars
- Verify signature present: "Best. Taimoor Alam" in message
- Verify URL present: "{calendly_url}" in message
- No placeholder tokens like {Token} remain
```

**LLM Model**: OpenAI (gpt-3.5-turbo or gpt-4)

**Temperature**: 0.7 (balance between creativity and consistency)

### Step 2: Token Substitution

After LLM generation:
1. Replace all `{Token}` placeholders with actual values
2. Remove any leftover template markers

### Step 3: Character Count Validation

```python
def validate_message_length(message: str, message_type: str) -> bool:
    limits = {
        "connection": 300,
        "inmail": 1900,
        "direct": 1000  # soft limit
    }
    limit = limits.get(message_type, limits["direct"])
    return len(message) <= limit
```

### Step 4: Signature Verification

```python
def validate_signature(message: str) -> bool:
    return "Best. Taimoor Alam" in message
```

### Step 5: URL Verification

```python
def validate_url_present(message: str, url: str) -> bool:
    return url in message
```

### Step 6: Placeholder Cleanup

```python
def has_remaining_tokens(message: str) -> bool:
    import re
    tokens = re.findall(r'\{[A-Z][a-zA-Z]+\}', message)
    return len(tokens) > 0
```

### Step 7: Retry Logic (if validation fails)

**Retry Strategy**:
- If length exceeded: Regenerate with stricter prompt ("MAX [limit-20] chars")
- If signature missing: Append automatically + log warning
- If URL missing: Append + regenerate CTA paragraph
- If tokens remain: Replace automatically + log warning

**Max Retries**: 3 attempts before fallback

**Fallback** (if all retries fail):
- Use pre-written template with minimal personalization
- Still include signature and Calendly URL
- Still validate character limit

---

## Storage & Persistence

### MongoDB Schema Addition

```javascript
// In level-2 collection, add to existing job documents:
{
  _id: ObjectId,
  job_id: string,
  // ... existing fields ...

  outreach_messages: {
    connection_request: {
      message: string,
      character_count: number,
      generated_at: ISODate,
      validated: boolean,
      validation_errors: [string]
    },
    inmail: {
      subject: string,
      body: string,
      character_count: number,
      generated_at: ISODate,
      validated: boolean,
      validation_errors: [string]
    }
  }
}
```

### File-Based Storage

```
applications/
└── <Company_Name>/
    └── <Role_Title>/
        ├── CV.md
        ├── cover_letter.txt
        ├── dossier.txt
        └── outreach.txt  // NEW - contains both connection + InMail
```

**File Format** (`outreach.txt`):
```
===== CONNECTION REQUEST =====
Character Count: 256/300
Valid: Yes

Hi Sarah, I saw your Product Manager role at Stripe...

===== INMAIL =====
Subject: Senior Backend Engineer - Database Performance Solution
Character Count: 847/1900
Valid: Yes

Hi Sarah,

I noticed Stripe's database query latency...
```

---

## Validation Checklist

**Pre-send Validation** (before saving to MongoDB or file):

- [ ] Message length ≤ 300 chars (connection) or ≤ 1900 chars (InMail)
- [ ] Signature "Best. Taimoor Alam" present
- [ ] Calendly URL included and valid (starts with http)
- [ ] {FirstName} replaced with actual contact name
- [ ] No remaining placeholder tokens ({Token})
- [ ] Grammar and spelling check (spell checker optional)
- [ ] No repetitive content from CV/cover letter
- [ ] Professional tone maintained
- [ ] Pain points referenced with specificity
- [ ] Clear call-to-action present

**Logging**:
```python
validation_result = {
    "message_id": str(uuid.uuid4()),
    "message_type": "connection|inmail",
    "character_count": len(message),
    "limit": 300 or 1900,
    "passed": all_checks_passed,
    "checks": {
        "length": True/False,
        "signature": True/False,
        "url": True/False,
        "no_tokens": True/False,
        "grammar": True/False
    },
    "errors": ["list of validation failures"],
    "timestamp": datetime.now().isoformat()
}
```

---

## Testing Strategy

### Unit Tests

| Test | Coverage |
|------|----------|
| Character count validation | All message types |
| Signature presence check | All message types |
| URL inclusion validation | All message types |
| Token replacement | All placeholders |
| Retry logic | Failure scenarios |

### Integration Tests

| Test | Coverage |
|------|----------|
| End-to-end message generation | Pipeline integration |
| MongoDB persistence | Storage layer |
| File output formatting | Output validation |

### Manual Validation

Before deploying to production:
1. Generate 5 connection requests (verify ≤ 300 chars)
2. Generate 5 InMails (verify ≤ 1900 chars for body)
3. Verify every message includes "Best. Taimoor Alam"
4. Verify every message includes Calendly URL
5. Verify no placeholder tokens remain
6. Test retry logic by intentionally creating oversized message

---

## Configuration

### Environment Variables

```bash
# .env
CALENDLY_URL=https://calendly.com/taimooralam/30min

# Optional
LINKEDIN_MESSAGE_MAX_RETRIES=3
LINKEDIN_CONNECTION_CHAR_LIMIT=300
LINKEDIN_INMAIL_CHAR_LIMIT=1900
LINKEDIN_INMAIL_SUBJECT_LIMIT=200
```

### Feature Flags

```python
# src/common/config.py
ENABLE_LINKEDIN_OUTREACH = True  # Enable LinkedIn message generation
VALIDATE_LINKEDIN_CHARS = True   # Enforce character limit validation
STORE_OUTREACH_MESSAGES = True   # Persist to MongoDB
```

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| LLM generates message too long | Message rejected by LinkedIn | Regenerate with stricter prompt, truncate if needed |
| Signature missing from message | Doesn't identify candidate | Validation catches, append automatically |
| Calendly URL missing | No meeting booking link | Validation catches, append automatically |
| Token not replaced | Message looks broken | Regex validation before send |
| Character count wrong (off-by-one) | Validation false positive | Use Python `len()` function, test with actual LinkedIn |

---

## Example Implementation

### Minimal Code Example

```python
from typing import Dict, List
import re

class LinkedInOutreachGenerator:
    def __init__(self, calendly_url: str):
        self.calendly_url = calendly_url
        self.limits = {
            "connection": 300,
            "inmail": 1900
        }

    def generate_connection_request(self,
                                    first_name: str,
                                    role: str,
                                    company: str,
                                    pain_point: str,
                                    value: str) -> Dict:
        """Generate LinkedIn connection request message."""

        # Step 1: Call LLM with strict character constraint
        prompt = f"""Generate a LinkedIn connection request (MAX {self.limits['connection']} chars).

Requirements:
- Greet {first_name}
- Reference their {role} role at {company}
- Mention {pain_point}
- Include value: {value}
- Include Calendly link: {self.calendly_url}
- End with signature: Best. Taimoor Alam
- MUST be ≤ {self.limits['connection']} characters

Message:"""

        message = self.llm_call(prompt)

        # Step 2: Validate
        validation = self.validate(message, "connection")

        if validation['passed']:
            return {
                'message': message,
                'validated': True,
                'character_count': len(message),
                'errors': []
            }
        else:
            # Step 3: Retry with stricter constraints
            return self.retry_generation(
                first_name, role, company, pain_point, value,
                "connection", attempt=1
            )

    def validate(self, message: str, message_type: str) -> Dict:
        """Validate message meets all requirements."""
        errors = []

        # Check length
        if len(message) > self.limits[message_type]:
            errors.append(f"Length {len(message)} exceeds limit {self.limits[message_type]}")

        # Check signature
        if "Best. Taimoor Alam" not in message:
            errors.append("Missing signature: 'Best. Taimoor Alam'")

        # Check URL
        if self.calendly_url not in message:
            errors.append(f"Missing Calendly URL: {self.calendly_url}")

        # Check for remaining tokens
        tokens = re.findall(r'\{[A-Z][a-zA-Z]+\}', message)
        if tokens:
            errors.append(f"Remaining tokens: {tokens}")

        return {
            'passed': len(errors) == 0,
            'errors': errors,
            'character_count': len(message)
        }
```

---

## Success Criteria

- [x] Documentation explicitly states 300 character limit for connection requests
- [x] Documentation explicitly states 1900 character limit for InMail body
- [x] Signature format documented as "Best. Taimoor Alam" (with period)
- [x] Signature placement documented for each message type
- [x] Calendly URL inclusion documented as mandatory
- [x] Message templates provided for both connection and InMail
- [x] Validation logic specified in detail
- [x] Character budgets calculated for each message type
- [x] Retry and fallback strategies documented
- [x] MongoDB schema and file-based storage documented
- [x] Testing strategy outlined
- [x] Configuration documented
