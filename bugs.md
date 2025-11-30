# Open Issues & Bugs

**Last Updated**: 2025-11-30 | **Format**: Status, Priority, Effort, Root Cause, Fix

---

## OPEN / CRITICAL

### Bug #12: Time-Based Quick Filters Not Working
**Status**: OPEN | **Priority**: HIGH | **Effort**: 2-3h
- Issue: 1h/3h/6h/12h filters return entire day instead of time range
- Components: `frontend/templates/index.html`, `frontend/app.py`, MongoDB `createdAt` field
- Root cause: MongoDB query timezone/format mismatch or frontend parameter not reaching backend
- Test: Check browser network tab, verify `createdAt` field format (ISO string vs timestamp), add debug logging
- Related: Time filter enhancement in `plans/missing.md`

### Bug #14: CV V2 Generation Adding Markdown Asterisks
**Status**: OPEN | **Priority**: HIGH | **Effort**: 2h
- Issue: Generated CV contains `**company**`, `**role**`, `**skill**` instead of plain text
- Components: `src/layer6_v2/types.py`, `src/layer6_v2/prompts/`, `src/layer6_v2/role_generator.py`
- Root cause: LLM prompts don't forbid markdown; `to_markdown()` methods add `**` syntax
- Fix: (1) Add "no markdown" instruction to all generation prompts, (2) Create `src/common/markdown_sanitizer.py`
- Test: Generate CV with 5+ roles; assert no `**`, `__`, `*`, `_` in output

### Bug #11: CV Editor Not Synced with Job Detail Page
**Status**: OPEN | **Priority**: HIGH | **Effort**: 2-3h
- Issue: Generated CV content (TipTap editor) doesn't display on job detail view
- Component: `frontend/templates/job_detail.html`
- Type: Component state/data flow integration issue
- Requires: Verify CV generation saves to correct state, link editor state to detail page renderer
- Discovered: 2025-11-30

---

## RESOLVED (Nov 2025)

- ✅ Process button not working (Fixed: added showToast, improved error handling)
- ✅ CV WYSIWYG sync issue (Fixed: replaced markdown with TipTap JSON rendering)
- ✅ PDF service unavailable (Fixed: updated CI/CD to copy docker-compose.runner.yml, added startup validation)
- ✅ Line spacing CSS not cascading (Fixed: changed child selectors to use `line-height: inherit`)
- ✅ Line spacing breaks in PDF with multiple companies (Fixed: `li` CSS updated to inherit line-height)

---

## Related Plan Documents

- `plans/missing.md` - Comprehensive gaps tracker
- `plans/linkedin-message-character-limit.md` - Character limit enforcement plan
- `plans/cv-generation-markdown-fix.md` - Detailed markdown sanitization plan
