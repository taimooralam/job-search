# Phase 5: WYSIWYG Page Break Visualization - Plan

**Created**: 2025-11-28
**Status**: Planning
**Estimated Duration**: 6-8 hours

---

## Overview

Add visual page break indicators to the CV editor and detail page to show users exactly where content will break across pages when exported to PDF. This prevents the surprise of discovering content cut-off after export and provides a WYSIWYG experience matching PDF output.

## Business Value

- **User Experience**: Users see exactly what they'll get in PDF before exporting
- **Prevents Surprises**: No more discovering content spread across unexpected pages in PDF
- **Professional Polish**: WYSIWYG editors are expected in modern document editors (Google Docs, Notion, Word)
- **Efficiency**: Faster CV iteration as users can immediately see page length

## Requirements

### Functional Requirements

1. **CV Editor (Editing Mode)**
   - Display horizontal visual page break indicators at page boundaries
   - Respect current page size setting (Letter vs A4)
   - Respect current margin settings (top, right, bottom, left)
   - Update dynamically as users edit content or change document styles
   - Visual indicator should be:
     - Clear and visible (gray line with label like "Page Break")
     - Not intrusive to editing experience
     - Positioned between page content areas

2. **CV Detail Page (View Mode)**
   - Display page breaks when viewing the CV in the job detail page main display
   - Match the page break positions shown in the editor
   - Respect page size and margin settings
   - Gives users preview of how the CV will look when printed/exported

3. **Dynamic Updates**
   - Page breaks recalculate when:
     - User edits content (text added/removed)
     - Font size changes
     - Line height changes
     - Margins change
     - Page size changes (Letter/A4)
   - Updates should be smooth and non-blocking (debounced if needed)

### Technical Requirements

1. **Page Dimension Calculation**
   - Letter: 8.5" × 11" (541.8px × 708px at 96 DPI) minus margins
   - A4: 210mm × 297mm (793px × 1123px at 96 DPI) minus margins
   - Account for top/bottom margins to determine available height

2. **Content Height Measurement**
   - Use `.getBoundingClientRect()` to measure element heights
   - Calculate cumulative height as user scrolls through content
   - Account for all TipTap node types (paragraphs, headings, lists, etc.)

3. **Break Calculation Strategy**
   - Calculate available page height = (page height - top margin - bottom margin)
   - Iterate through TipTap document, summing heights
   - Insert visual break indicator when cumulative height exceeds page height
   - Continue for multi-page documents

4. **Visual Implementation**
   - CSS approach: Insert decorative `<div>` or pseudo-element at break points
   - Or: Use CSS `page-break-after: always` pattern with visible indicator
   - Or: JavaScript-based, calculate and render break lines in real-time

## Architecture

### Data Flow

```
User edits CV (content, styles)
        ↓
Content change event fires
        ↓
Debounce (500ms)
        ↓
Calculate page breaks:
  - Get page dimensions (letter/a4)
  - Get margins (top, right, bottom, left)
  - Get line height, font size
  - Measure cumulative content height
  - Calculate break positions
        ↓
Render page break indicators:
  - Insert visual breaks in editor
  - Update main CV display with breaks
  - Apply CSS styling
        ↓
User sees page breaks in real-time
```

### Components

#### 1. Page Break Calculator (JavaScript)

```javascript
function calculatePageBreaks(editorState, pageSize, margins, styles) {
  // Returns array of pixel positions where breaks occur
  // Input: TipTap editor state, page dimensions, margins, document styles
  // Output: [breakY1, breakY2, breakY3, ...]
}
```

**Inputs**:
- `editorState`: TipTap document JSON
- `pageSize`: "letter" or "a4"
- `margins`: {top, right, bottom, left} in inches
- `styles`: {lineHeight, fontSize, fontFamily}

**Outputs**:
- Array of Y-pixel positions where page breaks occur
- Example: `[708, 1416, 2124]` for 3-page document

#### 2. Page Break Renderer (JavaScript)

```javascript
function renderPageBreaks(breakPositions) {
  // Insert visual break indicators at calculated positions
  // Updates DOM with page break dividers
}
```

**Responsibilities**:
- Create visual break line elements
- Position them at calculated Y coordinates
- Apply styling (gray line, "Page Break" label, etc.)
- Update on every page break recalculation

#### 3. Dynamic Update Handler

```javascript
function onEditorChange() {
  debounce(() => {
    const breaks = calculatePageBreaks(...);
    renderPageBreaks(breaks);
  }, 500);
}
```

**Triggers**:
- Content changes (user edits text)
- Document style changes (margins, line height, etc.)
- Page size changes (Letter/A4)
- Margin changes (any side)

### CSS Styling

```css
.page-break-indicator {
  position: absolute;
  width: 100%;
  height: 2px;
  background: linear-gradient(to right, #d0d0d0 30%, transparent 30%, transparent 70%, #d0d0d0 70%);
  border-top: 1px dashed #ccc;
  font-size: 0.75rem;
  color: #999;
  text-align: center;
  padding-top: 4px;
  left: 0;
  z-index: 10;
  pointer-events: none;
  user-select: none;
}

.page-break-indicator::before {
  content: "Page Break";
}
```

Or simpler:
```css
.page-break-indicator {
  height: 2px;
  background-color: #ddd;
  border-bottom: 1px dashed #ccc;
  margin: 8px 0;
  text-align: center;
  font-size: 0.75rem;
  color: #aaa;
}
```

## Implementation Phases

### Phase 5.1: Page Break Calculator (2 hours)

**Deliverables**:
- `calculatePageBreaks()` function in `cv-editor.js`
- Unit tests for various document lengths
- Support for Letter and A4 page sizes
- Account for margins in calculation

**Files to Modify**:
- `frontend/static/js/cv-editor.js` - Add calculator function
- `tests/frontend/test_cv_editor_phase5.py` - Unit tests

**Test Cases**:
- Single page (content fits on one page)
- Two pages (content exactly fills two pages)
- Three+ pages (longer documents)
- Different page sizes (Letter vs A4)
- Different margin combinations
- With/without headers/footers

### Phase 5.2: Page Break Renderer (2 hours)

**Deliverables**:
- `renderPageBreaks()` function to inject visual indicators
- CSS styling for page break lines
- Positioning logic for accurate placement
- Cleanup on re-render (avoid duplicate indicators)

**Files to Modify**:
- `frontend/static/js/cv-editor.js` - Add renderer function
- `frontend/templates/base.html` - Add CSS for page breaks
- `tests/frontend/test_cv_editor_phase5.py` - Unit tests

**Test Cases**:
- Visual breaks render at correct Y positions
- No duplicate breaks on re-render
- Breaks disappear when content shrinks
- Multiple breaks render correctly for long documents

### Phase 5.3: Dynamic Update Integration (2 hours)

**Deliverables**:
- Integrate page break calculation into content change handler
- Debounce updates (500ms) for performance
- Update on style changes (margins, line height, page size)
- Update on document style changes

**Files to Modify**:
- `frontend/static/js/cv-editor.js` - Hook into existing event handlers
- Update `saveEditorState()` and style change handlers
- `tests/frontend/test_cv_editor_phase5.py` - Integration tests

**Test Cases**:
- Page breaks update when content changes
- Page breaks update when margins change
- Page breaks update when line height changes
- Page breaks update when page size changes
- Debounce prevents excessive recalculation

### Phase 5.4: CV Detail Page Integration (1-2 hours)

**Deliverables**:
- Display page breaks in main CV display area
- Reuse page break calculation logic
- Support for viewing CVs with page breaks
- No editor required (read-only view)

**Files to Modify**:
- `frontend/templates/job_detail.html` - Add break rendering in CV display
- `frontend/static/js/cv-editor.js` - Extract page break logic for reuse
- `tests/frontend/test_cv_editor_phase5.py` - Integration tests

**Implementation**:
- Calculate page breaks from `cv_editor_state` in main display
- Render breaks in main CV area (not just editor)
- Style consistently with editor breaks
- Update when CV is loaded or content changes

### Phase 5.5: Testing & Polish (1-2 hours)

**Deliverables**:
- Comprehensive unit tests (Phase 5 test suite)
- E2E tests for page break visualization
- Cross-browser testing (Chrome, Firefox, Safari)
- Mobile responsiveness validation

**Files to Modify**:
- `tests/frontend/test_cv_editor_phase5.py` - Comprehensive test suite
- `.github/workflows/tests.yml` - Enable Phase 5 tests in CI
- `tests/e2e/test_cv_editor_e2e.py` - E2E tests for page breaks

**Test Coverage**:
- Calculator: 15+ tests
- Renderer: 10+ tests
- Integration: 15+ tests
- E2E: 10+ tests
- Total: 50+ new tests

## Technical Approach

### Option A: CSS-Based (RECOMMENDED)

**Pros**:
- Simple implementation
- Performant (CSS handles rendering)
- Easy to style and customize
- Works across browsers

**Cons**:
- Limited flexibility
- Harder to calculate exact break positions

**Implementation**:
```javascript
// Calculate break positions
// Insert transparent divs at positions with CSS styling
// Use CSS gradients for visual line effect
```

### Option B: JavaScript-Based (Canvas/SVG)

**Pros**:
- Maximum control over visual appearance
- Can draw complex indicators
- Smooth animations possible

**Cons**:
- More complex implementation
- Potential performance issues with many breaks
- Requires redraw on scroll/resize

**Implementation**:
- Use Canvas or SVG overlay
- Recalculate and redraw on content change

### Option C: DOM-Based (JAVASCRIPT + HTML)

**Pros**:
- Simple and maintainable
- Easy to debug
- No canvas/SVG complexity

**Cons**:
- Potential performance with many breaks
- DOM updates can be slow with large documents

**Implementation**:
- Create `<div class="page-break-indicator">` at each break point
- Position absolutely or use flexbox
- Update entire set on recalculation

## Dependencies

### Completed (Phase 3 & 4)
- Document margins (Phase 3)
- Page size selector (Phase 3)
- Line height control (Phase 3)
- PDF export with correct page breaks (Phase 4)

### Current
- TipTap editor with all Phase 1-4 features
- MongoDB persistence of document styles

### Needed for Phase 5
- None (all dependencies complete)

## Testing Strategy

### Unit Tests

1. **Calculator Tests** (15 tests)
   - Single page, two pages, three+ pages
   - Letter and A4 sizes
   - Various margin combinations
   - With headers/footers
   - Edge cases (empty document, very long single paragraph)

2. **Renderer Tests** (10 tests)
   - Breaks insert at correct positions
   - No duplicate breaks
   - Breaks cleanup correctly
   - CSS styling applied
   - Multiple breaks render correctly

3. **Integration Tests** (15 tests)
   - Content changes update breaks
   - Style changes update breaks
   - Debounce works correctly
   - No performance issues
   - Backward compatibility with Phase 1-4

### E2E Tests

1. **Editor Tests** (5 tests)
   - Load editor, see page breaks
   - Edit content, breaks update
   - Change margins, breaks update
   - Change page size, breaks update
   - Change line height, breaks update

2. **Detail Page Tests** (5 tests)
   - View CV with page breaks in detail page
   - Page breaks match editor
   - No page breaks in edit mode
   - Responsive on mobile

### Manual Testing

1. **Editor Workflow**
   - Create multi-page CV
   - Verify breaks appear
   - Edit content, verify breaks update
   - Export PDF, verify breaks match visualization

2. **Visual Validation**
   - Breaks not too intrusive
   - Clearly visible when needed
   - Doesn't interfere with editing
   - Professional appearance

## Success Criteria

- [ ] Page breaks calculated accurately for all document lengths
- [ ] Page breaks update dynamically as content changes
- [ ] Page breaks respect margin and page size settings
- [ ] Visual indicators are clear but not intrusive
- [ ] Works for Editor and Detail Page views
- [ ] 50+ new unit tests, all passing
- [ ] E2E tests validate functionality
- [ ] Cross-browser compatible (Chrome, Firefox, Safari)
- [ ] Mobile responsive
- [ ] PDF export page breaks match visualization
- [ ] Zero performance degradation in editor
- [ ] Phase 5 test suite passes in CI/CD

## Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|-----------|
| Complex calculation with deeply nested content | Medium | High | Use iterative approach (like Phase 4 PDF), extensive unit tests |
| Performance issues with large documents | Medium | Medium | Debounce updates, cache calculations, lazy render |
| Page breaks visible in PDF differ from visualization | Low | High | Comprehensive testing, align with Phase 4 PDF dimensions |
| Mobile display issues | Medium | Low | Responsive CSS, mobile-specific tests |
| Cross-browser compatibility | Low | Medium | Standard CSS, browser testing |

## Related Features

- **Phase 4**: PDF export (already respects page breaks correctly)
- **Phase 3**: Document styles (margins, page size, line height)
- **Phase 2**: Text formatting (affects height calculations)
- **Detail Page UI**: CV display area needs page break rendering

## Files to Create/Modify

### New Files
- `plans/phase5-page-break-visualization.md` (this file)
- `tests/frontend/test_cv_editor_phase5.py` (test suite)

### Modified Files
- `frontend/static/js/cv-editor.js` (calculator + renderer + integration)
- `frontend/templates/base.html` (CSS styling)
- `frontend/templates/job_detail.html` (integration in detail page)
- `frontend/app.py` (if API changes needed, unlikely)
- `tests/frontend/test_cv_editor_phase4.py` (cross-reference in Phase 4)

## Estimated Effort

| Phase | Duration | Effort |
|-------|----------|--------|
| 5.1: Calculator | 2 hours | High (algorithmic complexity) |
| 5.2: Renderer | 2 hours | Medium (DOM manipulation) |
| 5.3: Integration | 2 hours | Medium (event handling, debounce) |
| 5.4: Detail Page | 1-2 hours | Low (reuse logic) |
| 5.5: Testing | 1-2 hours | High (comprehensive coverage) |
| **Total** | **8-10 hours** | **Moderate** |

## Next Steps

1. Review this plan with team
2. Prioritize Phase 5 in roadmap
3. Assign to frontend-developer agent
4. Implement Phase 5.1 (calculator) first
5. Build test suite in parallel
6. Integrate into existing Phase 1-4 code
7. Re-enable E2E tests once complete

## Success Metrics

- Users can preview multi-page CVs before exporting
- No more surprises with page breaks in PDF
- Positive feedback on WYSIWYG experience
- Increased user engagement with CV editor
- Reduced support requests about unexpected page breaks

---

**Created by**: Documentation Sync Agent
**Date**: 2025-11-28
**Status**: Ready for implementation planning
