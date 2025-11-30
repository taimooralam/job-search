# CV Editor WYSIWYG Consistency Plan

**Created**: 2025-11-29
**Status**: Planning
**Priority**: Medium
**Related Requirement**: #2 from missing.md

---

## Problem Statement

The CV editor (`.ProseMirror`) and the detail page CV display (`#cv-markdown-display`) render content with different styles, breaking the WYSIWYG (What You See Is What You Get) experience.

### Symptoms

1. Font rendering differs between editor and display
2. Line height/spacing inconsistent
3. Margin/padding differences
4. Heading sizes may vary
5. List styling (bullets, numbering) differs

---

## Root Cause Analysis

### Current Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      EDITOR (TipTap)                            │
│  Location: CV Editor Side Panel                                 │
│  Container: .ProseMirror                                        │
│  CSS: base.html lines 284-461                                   │
│  JS: cv-editor.js                                               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                      [TipTap JSON State]
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    DISPLAY (Detail Page)                        │
│  Location: Job Detail Page main content                         │
│  Container: #cv-markdown-display                                │
│  Rendering: tiptapJsonToHtml() function                         │
│  CSS: Different/missing selectors                               │
└─────────────────────────────────────────────────────────────────┘
```

### Why Styles Differ

1. **Different CSS Contexts**: Editor uses `.ProseMirror` selectors; display uses `#cv-markdown-display`
2. **Separate CSS Rules**: Each has its own styling that evolved independently
3. **No Shared Style System**: No single source of truth for CV typography

---

## Proposed Solution

### Option A: Unified CSS Classes (Recommended)

Create a shared `.cv-content` class that both containers use:

```css
/* Shared CV content styles */
.cv-content h1 { font-size: 24px; font-weight: 700; margin-bottom: 0.5em; }
.cv-content h2 { font-size: 20px; font-weight: 600; margin-bottom: 0.4em; }
.cv-content h3 { font-size: 18px; font-weight: 600; margin-bottom: 0.3em; }
.cv-content p { font-size: 14px; line-height: 1.5; margin-bottom: 0.5em; }
.cv-content ul, .cv-content ol { margin-left: 1.5em; margin-bottom: 0.5em; }
.cv-content li { margin-bottom: 0.25em; }
.cv-content strong { font-weight: 700; }
.cv-content em { font-style: italic; }
.cv-content mark { background-color: yellow; padding: 0 2px; }
/* ... all formatting styles */
```

Then apply to both:

```html
<!-- Editor -->
<div class="ProseMirror cv-content">...</div>

<!-- Display -->
<div id="cv-markdown-display" class="cv-content">...</div>
```

### Option B: CSS Custom Properties

Use CSS variables for key values:

```css
:root {
  --cv-font-size-base: 14px;
  --cv-font-size-h1: 24px;
  --cv-font-size-h2: 20px;
  --cv-line-height: 1.5;
  --cv-spacing-paragraph: 0.5em;
}

.ProseMirror h1, #cv-markdown-display h1 {
  font-size: var(--cv-font-size-h1);
}
```

---

## Implementation Steps

### Phase 1: Audit Current Styles (1 hour)

1. Extract all `.ProseMirror` CSS rules from `base.html`
2. Extract all `#cv-markdown-display` CSS rules
3. Create comparison table showing differences
4. Identify which styles are "correct" (match PDF output)

### Phase 2: Create Unified Styles (2 hours)

1. Create `.cv-content` class with all required styles
2. Base styles on PDF output (the ultimate WYSIWYG target)
3. Include all formatting: fonts, sizes, colors, spacing, lists, etc.
4. Add to `base.html` in new section

### Phase 3: Apply to Both Containers (1 hour)

1. Add `.cv-content` class to `.ProseMirror` container
2. Add `.cv-content` class to `#cv-markdown-display`
3. Remove duplicate/conflicting CSS rules
4. Test both contexts render identically

### Phase 4: Test & Validate (2 hours)

1. Visual comparison: Editor vs Display vs PDF
2. Test all formatting: bold, italic, headings, lists, colors
3. Test document styles: margins, page size, line height
4. Cross-browser testing

---

## Files to Modify

| File | Changes |
|------|---------|
| `frontend/templates/base.html` | Add unified `.cv-content` CSS, cleanup duplicates |
| `frontend/templates/job_detail.html` | Add `.cv-content` class to display container |
| `frontend/static/js/cv-editor.js` | Ensure editor container has `.cv-content` class |

---

## Test Cases

1. **Typography**: Headings H1-H3 identical in both views
2. **Lists**: Bullets and numbers render same
3. **Formatting**: Bold, italic, underline, highlight consistent
4. **Spacing**: Line height, paragraph spacing match
5. **Fonts**: Font family and size identical
6. **Colors**: Text and highlight colors match
7. **Margins**: Document margins consistent (within padding)

---

## Success Criteria

- [ ] Editor content visually matches detail page display
- [ ] Both match PDF export output
- [ ] No duplicate CSS rules
- [ ] All formatting types tested and verified
- [ ] Cross-browser compatibility (Chrome, Firefox, Safari)

---

## Effort Estimate

**Total**: 4-6 hours

- Phase 1 (Audit): 1 hour
- Phase 2 (Create): 2 hours
- Phase 3 (Apply): 1 hour
- Phase 4 (Test): 2 hours

---

## Dependencies

- Phase 3 (Document Styles) complete ✅
- Phase 4 (PDF Export) complete ✅
- Understanding of TipTap JSON → HTML conversion

---

## Related Issues

- #4 Line Spacing in Editor (may be fixed as part of this)
- Phase 5.1 Page Break Visualization (uses same rendering)
