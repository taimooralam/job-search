# CV Rich Text Editor Phase 2 - Known Issues

**Last Updated**: 2025-11-27
**Status**: 2 HIGH PRIORITY ISSUES DISCOVERED (2025-11-27)
**Assignee**: frontend-developer (for implementation), test-generator (for test coverage)

**Issue Summary**:
- 2 HIGH PRIORITY (CV display not updating immediately, editor not WYSIWYG)
- Both are UX issues, not data integrity issues
- Both have clear root causes and straightforward fixes
- 38 unit tests already passing for Phase 2 features
**Total Open Issues**: 2

---

## Issue #1: CV Display Not Updating Immediately on Editor Close

**Severity**: HIGH (UX BLOCKER)
**Reported**: 2025-11-27 (Manual Testing - Post Phase 2 Completion)
**Status**: OPEN - IDENTIFIED ROOT CAUSE

**Description**:
When user closes the CV editor panel after making changes, the main CV display does not update immediately. Changes only appear after a full page reload.

**Expected Behavior**:
- User edits CV in TipTap editor
- User clicks "Save" or closes editor panel
- Main CV display (`#cv-markdown-display`) updates immediately with formatted content
- No page reload needed to see changes

**Actual Behavior**:
- User edits CV in TipTap editor
- User closes editor
- Main CV display stays unchanged (shows old content)
- Changes only appear after full page reload

**Root Cause Analysis**:
The API successfully saves the TipTap JSON state to MongoDB (`cv_editor_state` field), but the JavaScript in cv-editor.js does NOT:
1. Convert the saved TipTap JSON to HTML
2. Update the main CV display div (`#cv-markdown-display`) on editor close

The application currently only displays the `cv_text` field (markdown format), which isn't updated when the editor closes.

**Fix Needed**:
In `frontend/static/js/cv-editor.js`, add an event handler for when the editor panel closes:
1. Get the current TipTap editor content (in JSON format)
2. Convert TipTap JSON to HTML (using existing `tiptapJsonToHtml()` function from app.py)
3. Update the `#cv-markdown-display` div with the HTML
4. Optionally: Show success toast/message to confirm update

**Implementation Approach**:
```javascript
// Add to cv-editor.js:
// When editor closes or save completes, call:
const html = convertTipTapToHtml(editor.getJSON());
document.getElementById('cv-markdown-display').innerHTML = html;
```

**Files to Modify**:
- `frontend/static/js/cv-editor.js` - Add close handler and display update function
- `frontend/templates/job_detail.html` - May need to add event listener on close button
- Possibly: `frontend/app.py` - Expose `tiptapJsonToHtml()` as REST endpoint if needed

**Test Plan**:
1. Manual: Edit CV → Close editor → Verify display updates immediately
2. Manual: Edit multiple fields → Close → Check all changes visible
3. Manual: Reload page → Verify changes persisted
4. Unit test: Mock editor close event, verify display update called

**Priority**: HIGH - Impacts user experience directly
**Effort**: 1-2 hours (straightforward JavaScript/DOM update)

---

## Issue #2: TipTap Editor Not WYSIWYG - Text Formatting Not Visible

**Severity**: CRITICAL (UX BLOCKER)
**Reported**: 2025-11-27 (Manual Testing - Post Phase 2 Completion)
**Status**: OPEN - ROOT CAUSE IDENTIFIED

**Description**:
The TipTap editor does not display text formatting visually. Bold, italic, headings, and other formatting are stored in the data model but not rendered visually in the editor. User sees raw text, not styled text.

**Expected Behavior** (WYSIWYG):
- User types "Hello"
- User selects text and clicks Bold button
- Text appears bold in the editor (visual feedback)
- Text is also bold when saved and displayed

**Actual Behavior**:
- User types "Hello"
- User selects text and clicks Bold button
- Text appears unchanged in editor (no visual bold styling)
- Text IS saved as bold in MongoDB (metadata shows bold)
- Text does NOT appear bold when displayed (no CSS to render it)

**Root Cause Analysis**:
TipTap/ProseMirror requires CSS styling to render formatted text visually. The editor is missing CSS for the `.ProseMirror` content nodes. Without these styles:
- `.ProseMirror strong` - doesn't appear bold
- `.ProseMirror em` - doesn't appear italic
- `.ProseMirror h1` - doesn't appear as heading
- No visual feedback to user while editing

**Fix Needed**:
Add CSS styles for TipTap/ProseMirror content rendering. Options:

**Option A: Add CSS to base.html** (Recommended - Simple)
```html
<style>
.ProseMirror strong { font-weight: bold; }
.ProseMirror em { font-style: italic; }
.ProseMirror u { text-decoration: underline; }
.ProseMirror h1 { font-size: 2em; font-weight: bold; }
.ProseMirror h2 { font-size: 1.5em; font-weight: bold; }
.ProseMirror h3 { font-size: 1.25em; font-weight: bold; }
.ProseMirror ul { list-style-type: disc; padding-left: 2rem; }
.ProseMirror ol { list-style-type: decimal; padding-left: 2rem; }
/* Additional styles for highlight, alignment, indentation, font sizes, etc. */
</style>
```

**Option B: Add dedicated CSS file** (Cleaner for scale)
- Create `frontend/static/css/prosemirror-styles.css`
- Import in `base.html`
- Organize by node type (headings, lists, inline, alignment, etc.)

**Implementation Details**:
Must include styles for ALL Phase 2 features:
- [ ] Basic formatting (strong, em, u)
- [ ] Headings (h1-h6)
- [ ] Lists (ul, ol, li)
- [ ] Indentation (padding-left per level)
- [ ] Alignment (text-align: left/center/right/justify)
- [ ] Font families (custom font-family per selection)
- [ ] Font sizes (8-24pt)
- [ ] Highlight color (background-color)
- [ ] Code blocks (if supported)

**Files to Modify**:
- `frontend/templates/base.html` - Add <style> block or import css
- OR `frontend/static/css/prosemirror-styles.css` - Create new file with all styles

**Test Plan**:
1. Manual: Type text → Click Bold → Verify text appears bold visually
2. Manual: Type text → Click Italic → Verify text appears italic visually
3. Manual: Type text → Select heading level → Verify size/weight changes
4. Manual: Create list → Verify bullets/numbers appear
5. Manual: Change font → Verify font changes in editor
6. Manual: Change font size → Verify size changes in editor
7. Manual: Apply highlight → Verify background color appears
8. Unit test: Verify CSS classes applied correctly to ProseMirror nodes

**Priority**: CRITICAL - Blocks Phase 2 from being usable
**Effort**: 1-2 hours (CSS styling, testing across features)

---

## Resolution Path

### Phase 1: Fix Issues #1 and #2 (This Week)

**Issue #1 Priority: HIGH** (1-2 hours)
- **Assigned to**: frontend-developer
- **Tasks**:
  1. Add event handler for editor close/collapse in cv-editor.js
  2. Implement TipTap JSON to HTML conversion on close
  3. Update main CV display (`#cv-markdown-display`) with formatted content
  4. Test: Edit CV, close editor, verify display updates immediately
  5. Manual testing with full page reload verification

**Issue #2 Priority: CRITICAL** (1-2 hours)
- **Assigned to**: frontend-developer
- **Tasks**:
  1. Create `frontend/static/css/prosemirror-styles.css` with all formatting styles
  2. Add styles for: bold, italic, underline, headings, lists, alignment, fonts, sizes, highlight
  3. Import CSS in `frontend/templates/base.html`
  4. Test each formatting feature visually in editor
  5. Verify styles render correctly for all Phase 2 features
  6. Cross-browser testing (Chrome, Firefox, Safari)

### Phase 2: Add Test Coverage (After Fixes Complete)

**Assigned to**: test-generator
- **Tasks**:
  1. Write tests for Issue #1 fix (display update on close)
  2. Write tests for Issue #2 fix (CSS rendering verification)
  3. Add integration tests for editor close flow
  4. Add regression tests for Phase 1 features
  5. Ensure all 38+ Phase 2 tests pass with fixes

### Phase 3: Validation

**Steps**:
1. Manual regression testing with full user feedback
2. Cross-browser testing (Chrome, Firefox, Safari)
3. Mobile responsiveness check (if applicable)
4. All unit tests passing (38+ Phase 2 tests)
5. All integration tests passing
6. Phase 3 design can proceed once Phase 2 fully complete+tested

---

## References

- **Architecture Doc**: `plans/architecture.md` → "CV Rich Text Editor Phase 2" section
- **Implementation Tracker**: `plans/missing.md` → "Phase 2: Enhanced Text Formatting"
- **Code**: `frontend/static/js/cv-editor.js` (main editor logic)
- **API**: `frontend/app.py` (lines 1121-1475) → `/api/jobs/<job_id>/cv-editor` endpoints
- **Templates**: `frontend/templates/job_detail.html` (editor UI) and `base.html` (styles/CDN)

---

## Success Criteria for Phase 2 Resolution

Phase 2 is COMPLETE when BOTH issues are fixed and tested:

- [ ] **Issue #1 Fixed**: CV Display Updates Immediately
  - Editor close event triggers display update
  - TipTap JSON converted to HTML
  - Main CV display updates without page reload
  - All changes visible immediately
  - MongoDB persistence verified

- [ ] **Issue #2 Fixed**: Editor Is WYSIWYG
  - Bold text appears bold visually
  - Italic text appears italic visually
  - Headings appear at correct sizes
  - Lists show bullets/numbers
  - Custom fonts render in editor
  - Font sizes render in editor (8-24pt)
  - Highlight colors visible in editor
  - Text alignment visible in editor
  - Indentation visible in editor

- [ ] **Testing Complete**:
  - All 38 Phase 2 feature tests passing
  - Issue #1 integration tests passing
  - Issue #2 CSS rendering tests passing
  - Phase 1 regression tests passing (46 tests)
  - Manual end-to-end testing complete
  - Cross-browser testing complete

- [ ] **Documentation Updated**:
  - `plans/missing.md` Phase 2 marked COMPLETE+TESTED
  - `plans/cv-editor-phase2-issues.md` updated with resolution details
  - `plans/next-steps.md` updated with Phase 3 readiness
  - No unresolved issues remaining

**Current Status**: Issues identified and documented (2025-11-27)
**Next Action**: frontend-developer to implement Issue #1 and #2 fixes
**Timeline**: 2-4 hours implementation + testing
**Next Milestone**: Phase 2 COMPLETE AND FULLY TESTED
