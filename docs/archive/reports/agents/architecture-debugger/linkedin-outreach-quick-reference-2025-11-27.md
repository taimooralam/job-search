# LinkedIn Outreach Generation - Quick Reference

**Last Updated**: 2025-11-27
**Status**: Requirements finalized and documented

---

## Character Limits (HARD LIMITS)

```
CONNECTION REQUEST
┌─────────────────────────────────┐
│ Maximum: 300 characters         │
│ LinkedIn enforces (rejects if >) │
└─────────────────────────────────┘

INMAIL MESSAGE
┌─────────────────────────────────┐
│ Subject: 200 characters         │
│ Body: 1900 characters           │
│ LinkedIn enforces (truncates)    │
└─────────────────────────────────┘
```

---

## Mandatory Signature (EVERY MESSAGE)

```
Format (exact):
  Best. Taimoor Alam

Location:
  Connection Request:  After Calendly URL
  InMail:              At end of message body
```

---

## Calendly URL (REQUIRED)

```
Source:    Environment variable CALENDLY_URL
Format:    https://calendly.com/taimooralam/30min
Required:  In every outreach message
Location:  Before signature (connections) or in CTA (InMail)
```

---

## Connection Request Template (300 char budget)

```
Hi {FirstName}, [hook about pain point]. [value statement].
Book time: {CalendlyURL}. Best. Taimoor Alam

Character Budget:
├─ Greeting:    9 chars    ("Hi John, ")
├─ Hook:        80-100 chars
├─ Value:       50-70 chars
├─ CTA:         11 chars   ("Book time: ")
├─ URL:         40-50 chars
└─ Signature:   19 chars   ("Best. Taimoor Alam")
   ────────────────────────
   Total:      ~209-259 chars (41-91 char buffer)
```

---

## InMail Template (1900 char body budget)

```
Subject: {Role} - {PainPoint} Solution [max 200 chars]

Hi {FirstName},

[Paragraph 1: Hook with specific pain point or achievement]

[Paragraph 2: Value with 1-2 STAR examples mapped to their needs]

[Paragraph 3: Call-to-action with Calendly link]

Best. Taimoor Alam
{CalendlyURL}

Character Budget:
├─ Subject:     ~50 chars  (well under 200 limit)
├─ Greeting:    ~20 chars
├─ Para 1:      150-200 chars
├─ Para 2:      400-500 chars
├─ Para 3:      150-200 chars
└─ Signature:   ~70 chars
   ────────────────────────
   Total:      ~950 chars (950 char buffer to 1900 limit)
```

---

## Validation Checklist

Pre-send validation (REQUIRED):

- [ ] Message length ≤ 300 chars (connection) or ≤ 1900 chars (InMail body)
- [ ] Signature "Best. Taimoor Alam" present
- [ ] Calendly URL included and valid
- [ ] All {Token} placeholders replaced
- [ ] No remaining tokens like {Role}, {Company}
- [ ] Professional tone
- [ ] Pain points referenced with specificity
- [ ] Clear call-to-action
- [ ] No emojis or formatting characters
- [ ] Grammar and spelling correct

---

## Personalization Tokens

| Token | Source | Required? | Fallback |
|-------|--------|-----------|----------|
| {FirstName} | Layer 5 | YES | "there" |
| {Role} | Job posting | YES | Skip mention |
| {Company} | Job posting | YES | Skip mention |
| {PainPoint} | Layer 2 | YES | Generic pain point |
| {Value} | Layer 4/STAR | For connections | Skip if unavailable |
| {CalendlyURL} | Environment | YES | Fail validation |

---

## Retry Logic (if validation fails)

```
Validation PASS → Save to MongoDB + File
            ↓
Validation FAIL
            ↓
Attempt 1: Regenerate with stricter prompt
       ├─ PASS → Save
       └─ FAIL → Attempt 2
            ↓
Attempt 2: Regenerate with even stricter constraints
       ├─ PASS → Save
       └─ FAIL → Attempt 3
            ↓
Attempt 3: Truncate + Validate + Save
       ├─ PASS → Save (logged)
       └─ FAIL → Fallback template
```

---

## File & MongoDB Persistence

```
MongoDB (level-2 collection):
└── outreach_messages: {
    connection_request: {
      message: string,
      character_count: number,
      validated: boolean,
      validation_errors: [string]
    },
    inmail: {
      subject: string,
      body: string,
      character_count: number,
      validated: boolean,
      validation_errors: [string]
    }
  }

File System:
applications/
└── <Company>/
    └── <Role>/
        └── outreach.txt
```

---

## Configuration (.env)

```bash
CALENDLY_URL=https://calendly.com/taimooralam/30min

# Optional
LINKEDIN_MESSAGE_MAX_RETRIES=3
LINKEDIN_CONNECTION_CHAR_LIMIT=300
LINKEDIN_INMAIL_CHAR_LIMIT=1900
```

---

## Key Implementation Notes

1. **Signature is NOT optional**: Every message MUST end with "Best. Taimoor Alam"

2. **URL is MANDATORY**: Every message MUST include the Calendly URL

3. **Character limits are HARD**: Connection requests must be ≤ 300 chars exactly

4. **Validation is critical**: Check all requirements before saving

5. **Retries should be smart**: Use progressively stricter prompts

6. **Fallback templates**: Have pre-written templates for when LLM fails

---

## Success Metrics

After implementing Layer 6 outreach generation:

- [ ] All generated connection requests are ≤ 300 characters
- [ ] All generated InMails are ≤ 1900 characters (body)
- [ ] Every message contains "Best. Taimoor Alam"
- [ ] Every message contains the Calendly URL
- [ ] No placeholder tokens remain in final messages
- [ ] At least 3 retry attempts before fallback
- [ ] Messages saved to both MongoDB and filesystem
- [ ] Validation errors logged with message context

---

## Documentation References

- **ROADMAP.md**: High-level specification
- **plans/architecture.md**: Layer 6 technical details
- **plans/layer6-linkedin-outreach.md**: Complete implementation guide
- **plans/missing.md**: Implementation tracking

All documents maintained in sync with these requirements.

---

**For implementation questions, see plans/layer6-linkedin-outreach.md**
