# CV Editor UX Fixes - Testing Guide

## Fixes Implemented

### Fix #1: WYSIWYG Editor CSS (CRITICAL)
**Problem**: Text formatting (bold, italic, headings) not visible in editor
**Solution**: Added comprehensive `.ProseMirror` CSS styling to `base.html`

**CSS Added**:
- ✅ Headings (h1, h2, h3) with proper sizing and font-weight
- ✅ Bold (`<strong>`) → font-weight: bold
- ✅ Italic (`<em>`) → font-style: italic
- ✅ Underline (`<u>`) → text-decoration: underline
- ✅ Lists (ul, ol) with proper indentation and bullets
- ✅ Text alignment (left, center, right, justify)
- ✅ Highlight/mark → yellow background
- ✅ Code blocks and inline code
- ✅ Blockquotes, links, selection styles

### Fix #2: Immediate CV Display Update
**Problem**: Changes save to MongoDB but don't appear in main display until page reload
**Solution**: Added `updateMainCVDisplay()` function in `cv-editor.js`

**Implementation**:
- `closeCVEditorPanel()` now calls `updateMainCVDisplay()`
- Uses `editor.getHTML()` to get formatted HTML from TipTap
- Updates `#cv-markdown-display` with HTML content
- Also converts HTML → Markdown for backward compatibility with textarea
- Includes `htmlToMarkdown()` and `processNodeToMarkdown()` helper functions

---

## Testing Instructions

### Test #1: WYSIWYG Formatting Visibility

1. **Open Editor**:
   ```
   Navigate to: http://localhost:5000/job/<job_id>
   Click "Edit CV" button
   ```

2. **Test Bold**:
   - Type some text
   - Select text
   - Click **B** button
   - ✅ **EXPECTED**: Text should appear bold immediately
   - ❌ **BEFORE FIX**: Text stayed plain, only JSON metadata changed

3. **Test Italic**:
   - Select text
   - Click **I** button
   - ✅ **EXPECTED**: Text should appear italic immediately

4. **Test Underline**:
   - Select text
   - Click **U** button
   - ✅ **EXPECTED**: Text should show underline immediately

5. **Test Headings**:
   - Type a new line
   - Click **H1** button
   - Type "My Name"
   - ✅ **EXPECTED**: Text should be large and bold (2em font-size)
   - Click **H2** button
   - Type "Experience"
   - ✅ **EXPECTED**: Slightly smaller, still bold (1.5em font-size)

6. **Test Lists**:
   - Click **• List** button
   - Type "First item" and press Enter
   - Type "Second item"
   - ✅ **EXPECTED**: Should show bullet points with proper indentation

7. **Test Text Alignment**:
   - Select text
   - Click center alignment button (↔)
   - ✅ **EXPECTED**: Text should center immediately

8. **Test Highlight**:
   - Select text
   - Click highlight button (🖍)
   - ✅ **EXPECTED**: Text should have yellow background

### Test #2: Immediate Display Update on Close

1. **Open Editor**:
   ```
   Navigate to: http://localhost:5000/job/<job_id>
   Click "Edit CV" button
   ```

2. **Make Changes**:
   - Add bold text: **"Senior Software Engineer"**
   - Add a heading: **## EXPERIENCE**
   - Add a bullet list with 3 items
   - Wait 3 seconds for auto-save indicator to show "● Saved"

3. **Close Editor**:
   - Click the **X** button or click overlay to close

4. **Check Main Display**:
   - ✅ **EXPECTED**: Main CV display should show changes immediately
   - Bold text should be bold
   - Heading should be larger
   - Bullet list should show bullets
   - ❌ **BEFORE FIX**: Display showed old content, required page reload

5. **Verify Persistence**:
   - Reload page (Ctrl+R)
   - ✅ **EXPECTED**: Changes should still be there
   - Open editor again
   - ✅ **EXPECTED**: Editor should restore your formatting

### Test #3: Integration Test (Both Fixes Together)

1. **Full Workflow**:
   - Open editor
   - Type a complete CV section:
     ```
     ## PROFESSIONAL EXPERIENCE

     **Senior Software Engineer** | TechCorp | 2020-Present

     - Led team of 5 engineers building scalable microservices
     - Improved performance by **40%** through optimization
     - Implemented CI/CD pipeline reducing deployment time by 60%
     ```
   - Use all formatting: headings, bold, lists
   - Wait for auto-save
   - Close editor

2. **Verify WYSIWYG**:
   - ✅ Heading was large while typing
   - ✅ Bold text appeared bold in editor
   - ✅ Bullets showed immediately

3. **Verify Immediate Update**:
   - ✅ Main display shows formatted content immediately
   - ✅ No page reload needed
   - ✅ Formatting preserved

### Test #4: Edge Cases

1. **Empty Editor**:
   - Open editor on job with no CV
   - ✅ Should show default template
   - ✅ Formatting should work

2. **Large Document**:
   - Create CV with 10+ sections
   - ✅ All sections should format correctly
   - ✅ Scrolling should work smoothly

3. **Mixed Formatting**:
   - Create text with bold + italic + underline
   - ✅ All should stack correctly

4. **List Nesting**:
   - Create nested bullet lists (Tab key)
   - ✅ Indentation should increase
   - ✅ Sub-bullets should show

---

## Success Criteria

### WYSIWYG Fix
- [ ] Bold button makes text bold immediately
- [ ] Italic button makes text italic immediately
- [ ] Underline button adds underline immediately
- [ ] H1/H2/H3 buttons make text larger/bold immediately
- [ ] List buttons add bullets/numbers immediately
- [ ] Text alignment changes immediately
- [ ] Highlight adds yellow background immediately

### Immediate Update Fix
- [ ] Closing editor updates main display without reload
- [ ] Bold text appears bold in main display
- [ ] Headings appear larger in main display
- [ ] Lists show bullets in main display
- [ ] All formatting preserved after close
- [ ] Changes persist after page reload
- [ ] HTML → Markdown conversion works for backward compatibility

---

## Rollback Plan (if needed)

### WYSIWYG CSS Rollback:
```bash
# Remove lines 284-461 from base.html
# (The entire ProseMirror CSS block)
```

### Immediate Update Rollback:
```bash
# In cv-editor.js, revert closeCVEditorPanel() to:
function closeCVEditorPanel() {
    const panel = document.getElementById('cv-editor-panel');
    const overlay = document.getElementById('cv-editor-overlay');

    if (panel && overlay) {
        panel.classList.add('translate-x-full');
        setTimeout(() => {
            overlay.classList.add('hidden');
        }, 300);
    }
}

# Remove: updateMainCVDisplay(), htmlToMarkdown(), processNodeToMarkdown()
```

---

## Known Limitations

1. **HTML → Markdown Conversion**:
   - Basic conversion only
   - Complex nesting may lose some formatting
   - TipTap-specific features (font size, colors) not fully preserved in markdown

2. **Legacy Textarea Editor**:
   - Still exists for backward compatibility
   - May show slightly different formatting than TipTap

3. **Auto-save Timing**:
   - 3-second delay before save
   - Closing immediately after edit may not save (but unlikely in practice)

---

## Browser Compatibility

Tested CSS features require:
- Modern browsers (Chrome 90+, Firefox 88+, Safari 14+, Edge 90+)
- CSS Grid and Flexbox support
- `::selection` pseudo-element
- ES6 JavaScript (arrow functions, template literals, forEach)

---

## Performance Notes

- CSS is inline in `<head>` → loads immediately, no extra HTTP request
- JavaScript functions are lightweight (< 100 lines total)
- HTML → Markdown conversion is O(n) where n = number of nodes
- No external dependencies added

---

## Files Modified

1. **`/Users/ala0001t/pers/projects/job-search/frontend/templates/base.html`**
   - Added 177 lines of `.ProseMirror` CSS (lines 284-461)
   - Location: Inside `<style>` tag in `<head>`

2. **`/Users/ala0001t/pers/projects/job-search/frontend/static/js/cv-editor.js`**
   - Modified `closeCVEditorPanel()` function (line 550-572)
   - Added `updateMainCVDisplay()` function (line 574-608)
   - Added `htmlToMarkdown()` function (line 610-626)
   - Added `processNodeToMarkdown()` function (line 628-701)
   - Total: 150+ lines added/modified

---

## Next Steps After Testing

If tests pass:
1. ✅ Mark both issues as resolved
2. Update `plans/cv-editor-phase2-issues.md`
3. Consider removing legacy textarea editor (future cleanup)
4. Add unit tests for `htmlToMarkdown()` function

If tests fail:
1. Check browser console for errors
2. Verify TipTap loaded correctly (check for `window.tiptap`)
3. Use browser DevTools to inspect CSS application
4. Check `cvEditorInstance` is initialized before close
