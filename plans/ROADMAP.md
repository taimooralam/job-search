# Roadmap (Nov 2025)

> **See also**:
> - `plans/architecture.md` - System architecture
> - `plans/next-steps.md` - Immediate action items
> - `plans/missing.md` - Implementation gaps

---

## Current State

The 7-layer LangGraph pipeline is **fully implemented**:

| Layer | Component | Status |
|-------|-----------|--------|
| 2 | Pain Point Miner | Complete |
| 2.5 | STAR Selector | Complete (disabled by default) |
| 3 | Company Researcher | Complete |
| 3.5 | Role Researcher | Complete |
| 4 | Opportunity Mapper | Complete |
| 5 | People Mapper | Complete (SEO queries + synthetic fallback) |
| 6 | CV & Cover Letter Generator | Complete |
| 7 | Publisher | Complete |

**Infrastructure**:
- Runner Service: Complete (FastAPI, subprocess, JWT auth)
- Frontend: Complete (Flask/HTMX, process buttons, SSE logs)
- CI/CD: Complete (GitHub Actions for runner + frontend)

---

## LinkedIn Outreach Generation Specification

### Character Limits (CRITICAL)

All LinkedIn outreach messages must respect character limits enforced by LinkedIn:

| Message Type | Character Limit | Status |
|--------------|-----------------|--------|
| Connection Request | **300 characters** (HARD LIMIT) | Enforced in Layer 6 |
| InMail Body | **1900 characters** (HARD LIMIT) | Enforced in Layer 6 |
| InMail Subject | **200 characters** (HARD LIMIT) | Enforced in Layer 6 |
| Direct Message | No hard limit | Recommend 500-1000 chars |

### Mandatory Signature

All generated messages MUST include:
```
Best. Taimoor Alam
```
- **Format**: Exactly as shown (with period after "Best")
- **Placement**: After Calendly URL (connection requests) or at end of message (InMail)
- **Non-negotiable**: Signature must be in EVERY outreach message

### Calendly URL

- **Required in**: All connection requests and InMail call-to-action paragraphs
- **Source**: Environment variable `CALENDLY_URL` or config default
- **Format**: Full URL (e.g., `https://calendly.com/taimooralam/30min`)
- **Placement**: Before signature in connection requests

### Message Templates

**Connection Request (300 char limit)**:
```
Hi {FirstName}, I saw your {Role} role at {Company} and your work on {PainPoint}. I'd love to connect and discuss how I can help with {Value}. Book time: {CalendlyURL} Best. Taimoor Alam
```

**InMail (1900 char body limit)**:
```
Subject: {Role} - {PainPoint} Solution Architect

Hi {FirstName},

{Paragraph 1: Hook - reference specific pain point or achievement}

{Paragraph 2: Value - map candidate's relevant experience to their needs}

{Paragraph 3: Call-to-action - Calendly link and next steps}

Best. Taimoor Alam
{CalendlyURL}
```

### Validation

Pre-send validation (enforced in Layer 6):
- Message length ≤ 300 chars (connection) or ≤ 1900 chars (InMail)
- Signature "Best. Taimoor Alam" present
- Calendly URL included
- No placeholder tokens remaining
- Professional grammar and spelling

---

## Immediate Priorities

See `plans/next-steps.md` for detailed steps:

1. **Fix Anthropic credits** or switch to OpenAI for CV generation
2. **Run local pipeline smoke test**
3. **Configure VPS and Vercel environment variables**
4. **Deploy and verify end-to-end**

---

## Future Enhancements (Backlog)

### High Value
- [ ] Add mocking to CV generator tests (avoid real API calls in CI)
- [ ] Structured logging with run_id tagging
- [ ] Cost tracking per pipeline run

### Medium Value
- [ ] STAR selector with embeddings and caching
- [ ] Enable FireCrawl contact discovery (currently synthetic)
- [ ] .docx CV export
- [ ] Pipeline runs collection for history

### Lower Priority
- [ ] Layer 1.5: Application form mining
- [ ] Tiered execution and batch processing
- [ ] Knowledge graph edges for STAR records
- [ ] Google Drive/Sheets publishing (currently local only)

---

## Test Coverage

| Area | Tests | Status |
|------|-------|--------|
| Unit tests (core) | 135+ | Passing |
| Runner service | 18+ | Passing |
| Frontend | 32 | Passing |
| CV generator | 21 | Need mocking (API calls) |
| Integration | - | Not in CI |
