# Pipeline Progress Indicator - Testing Guide

## Quick Start Testing

### 1. Visual Inspection (No Backend Required)

Open the job detail page in a browser and use browser DevTools to manually trigger the progress indicator:

```javascript
// Open browser console on job detail page
// Show the progress container
document.getElementById('pipeline-progress-container').classList.remove('hidden');

// Simulate layer execution
updatePipelineStep('intake', 'executing');
setTimeout(() => updatePipelineStep('intake', 'success', null, 2.5), 2000);

setTimeout(() => updatePipelineStep('pain_points', 'executing'), 2500);
setTimeout(() => updatePipelineStep('pain_points', 'success', null, 3.1), 5000);

setTimeout(() => updatePipelineStep('company_research', 'executing'), 5500);
setTimeout(() => updatePipelineStep('company_research', 'failed', 'API rate limit exceeded', 1.2), 7000);

// Update overall progress
updateOverallProgress(43);
```

### 2. Responsive Design Testing

Test the UI at different viewport sizes:

| Device | Width | Expected Behavior |
|--------|-------|-------------------|
| Mobile (Portrait) | 375px | Step icons 36px, single column layout, hidden connector lines |
| Mobile (Landscape) | 667px | Step icons 40px, compact spacing |
| Tablet | 768px | Step icons 48px, full spacing |
| Desktop | 1024px+ | Full design with all metadata visible |

**Browser DevTools Method:**

1. Open DevTools (F12)
2. Click "Toggle Device Toolbar" (Ctrl+Shift+M)
3. Select device: iPhone SE (375px), iPad (768px), Desktop (1024px)
4. Verify stepper components resize correctly
5. Check touch targets are at least 44x44px on mobile

### 3. Animation Testing

Verify animations work correctly:

**Pulse Animation (Executing State):**
```javascript
// Should see pulsing ring around icon
updatePipelineStep('intake', 'executing');
```

**Progress Bar Shimmer:**
```javascript
// Should see shimmer effect on progress bar
updateOverallProgress(50);
```

**Auto-Scroll:**
```javascript
// Should scroll to step when it becomes active
updatePipelineStep('people_mapping', 'executing');
```

**Reduced Motion Support:**
```css
/* Test with browser setting: prefers-reduced-motion: reduce */
/* Animations should be disabled */
```

### 4. Accessibility Testing

**Keyboard Navigation:**
- Tab through all interactive elements (buttons, links)
- Verify focus indicators are visible
- Check focus order is logical (top to bottom)

**Screen Reader Testing:**

```html
<!-- Verify ARIA labels exist -->
<button aria-label="Show logs">Show</button>

<!-- Verify step status is announced -->
<div class="step-status" role="status" aria-live="polite">
  Executing...
</div>
```

**Color Contrast:**
- Verify all text meets WCAG AA standard (4.5:1 ratio)
- Test with Chrome DevTools → Lighthouse → Accessibility
- Use browser extension: Axe DevTools or WAVE

### 5. Integration Testing with Backend

Once backend SSE endpoint is implemented:

**Step 1: Start Local Development Server**

```bash
cd /Users/ala0001t/pers/projects/job-search/frontend
source ../.venv/bin/activate
python app.py
```

**Step 2: Navigate to Job Detail Page**

```
http://localhost:5000/job/{job_id}
```

**Step 3: Click "Process Job" Button**

Expected behavior:
1. Progress container becomes visible
2. Overall progress bar shows 0%
3. All steps show "Pending" state
4. SSE connection established (check Network tab)
5. Steps update in real-time as backend emits events
6. Logs appear in terminal (if "Show" is clicked)

**Step 4: Monitor Network Traffic**

```
DevTools → Network → Filter: event-stream
```

Expected SSE events:
```
data: {"layer": "intake", "status": "executing", "index": 0}
data: {"layer": "intake", "status": "success", "index": 0, "duration": 2.5}
...
```

**Step 5: Test Error Handling**

Simulate backend failure:
```javascript
// Manually trigger failed state
updatePipelineStep('company_research', 'failed', 'Connection timeout after 30s', 30.2);
```

Expected behavior:
- Step shows red background
- Error message appears below step
- Toast notification displays error

### 6. Performance Testing

**Metric Goals:**

| Metric | Target | Measurement |
|--------|--------|-------------|
| Initial Load | < 100ms | Time to show progress container |
| Step Update | < 50ms | Time to update step status |
| Animation FPS | 60 FPS | No janky animations |
| Memory Usage | < 10MB increase | Chrome DevTools → Performance |

**Performance Profiling:**

```javascript
// Measure step update performance
console.time('updatePipelineStep');
updatePipelineStep('intake', 'success');
console.timeEnd('updatePipelineStep');
// Expected: < 5ms
```

### 7. Cross-Browser Testing

Test on the following browsers:

- [ ] Chrome/Edge (Chromium) - latest
- [ ] Firefox - latest
- [ ] Safari - latest (macOS/iOS)
- [ ] Mobile Safari (iOS 15+)
- [ ] Chrome Mobile (Android)

**Known Issues to Check:**

1. **Safari SSE**: Verify EventSource works on Safari
2. **Mobile Chrome**: Check touch event handling
3. **Firefox**: Verify CSS animations work
4. **iOS Safari**: Check viewport sizing

### 8. End-to-End Testing Scenario

**Scenario: User processes a job and pipeline completes successfully**

```
Given I am on the job detail page
When I click "Process Job" button
Then I see the pipeline progress indicator
And all 7 steps show "Pending" status
And overall progress is 0%

When the backend starts processing layer 1
Then layer 1 shows "Executing..." status
And layer 1 has a pulsing blue icon
And overall progress is ~7%

When layer 1 completes successfully
Then layer 1 shows "Complete" status
And layer 1 has a green checkmark icon
And duration is displayed (e.g., "2.5s")

When layer 2 starts processing
Then layer 2 shows "Executing..." status
And the page auto-scrolls to layer 2

[Repeat for all 7 layers]

When all layers complete
Then overall progress is 100%
And I see a success toast notification
And the page reloads after 3 seconds
```

**Scenario: User processes a job and layer 3 fails**

```
Given the pipeline is running
And layers 1 and 2 have completed successfully

When layer 3 fails with error "API rate limit exceeded"
Then layer 3 shows "Failed" status
And layer 3 has a red X icon
And error message is displayed below layer 3
And I see an error toast notification
And polling stops
And page does NOT reload
```

### 9. Logs Testing

**Show/Hide Logs:**

```javascript
// Logs start hidden
document.getElementById('logs-container').classList.contains('hidden'); // true

// Click "Show" button
toggleLogsFull();

// Logs are visible
document.getElementById('logs-container').classList.contains('hidden'); // false

// Button text changes to "Hide"
document.getElementById('logs-toggle-text').textContent; // "Hide"
```

**Log Streaming:**

Verify logs auto-scroll to bottom as new lines arrive:

```javascript
// Simulate log arrival
const logsContent = document.getElementById('logs-content');
const logsContainer = document.getElementById('logs-container');

// Add 100 log lines
for (let i = 0; i < 100; i++) {
  const logLine = document.createElement('div');
  logLine.textContent = `[${new Date().toISOString()}] Log line ${i}`;
  logsContent.appendChild(logLine);
}

// Should auto-scroll to bottom
logsContainer.scrollTop === logsContainer.scrollHeight; // true
```

### 10. Manual Test Checklist

Print this checklist and test each item:

#### Visual Design
- [ ] All 7 steps are visible
- [ ] Step icons show numbers 1-7
- [ ] Step titles match specification
- [ ] Step descriptions are readable
- [ ] Overall progress bar is visible
- [ ] Run ID is displayed in header
- [ ] Logs terminal is present (hidden by default)

#### Interactive Elements
- [ ] "Process Job" button triggers progress indicator
- [ ] "Show/Hide" logs button works
- [ ] Clicking layer doesn't break UI
- [ ] Toast notifications appear and disappear

#### Status States
- [ ] Pending: Gray background, gray icon
- [ ] Executing: Blue gradient background, pulsing icon
- [ ] Success: Green gradient background, checkmark icon
- [ ] Failed: Red gradient background, X icon
- [ ] Error message appears on failed steps

#### Responsive Design
- [ ] Works on mobile (375px width)
- [ ] Works on tablet (768px width)
- [ ] Works on desktop (1024px+ width)
- [ ] Touch targets are at least 44x44px on mobile
- [ ] Text is readable at all sizes

#### Accessibility
- [ ] Can navigate with keyboard only
- [ ] Focus indicators are visible
- [ ] Screen reader announces status changes
- [ ] Color contrast meets WCAG AA
- [ ] Reduced motion preference is respected

#### Performance
- [ ] No jank when updating steps
- [ ] Animations run at 60 FPS
- [ ] Page remains responsive during polling
- [ ] Memory usage stays stable

#### Error Handling
- [ ] SSE connection failure falls back to polling
- [ ] Failed steps show error messages
- [ ] Network errors don't break UI
- [ ] Polling stops when pipeline completes/fails

---

## Automated Testing (Future)

### Playwright Test Example

```javascript
// tests/pipeline-progress.spec.js
import { test, expect } from '@playwright/test';

test('pipeline progress indicator displays and updates', async ({ page }) => {
  // Navigate to job detail page
  await page.goto('/job/test-job-id');

  // Click "Process Job" button
  await page.click('button:has-text("Process Job")');

  // Verify progress indicator appears
  const progressContainer = page.locator('#pipeline-progress-container');
  await expect(progressContainer).toBeVisible();

  // Verify all 7 steps are present
  const steps = page.locator('.pipeline-step');
  await expect(steps).toHaveCount(7);

  // Verify initial state is "Pending"
  const firstStep = steps.first();
  await expect(firstStep).toHaveClass(/pending/);

  // Mock SSE events and verify updates
  await page.route('/api/runner/jobs/*/progress', route => {
    route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: 'data: {"layer":"intake","status":"executing","index":0}\n\n'
    });
  });

  // Verify step updates to "Executing"
  await expect(firstStep).toHaveClass(/executing/, { timeout: 3000 });
});
```

### Jest Unit Test Example

```javascript
// tests/unit/pipeline-progress.test.js
describe('Pipeline Progress Functions', () => {
  test('updatePipelineStep updates step status', () => {
    document.body.innerHTML = `
      <li class="pipeline-step pending" data-layer="intake">
        <div class="step-status">Pending</div>
        <div class="step-error"></div>
      </li>
    `;

    updatePipelineStep('intake', 'success', null, 2.5);

    const step = document.querySelector('[data-layer="intake"]');
    expect(step.classList.contains('success')).toBe(true);
    expect(step.querySelector('.step-status').textContent).toBe('Complete');
  });

  test('formatDuration converts seconds to human-readable format', () => {
    expect(formatDuration(0.5)).toBe('<1s');
    expect(formatDuration(30)).toBe('30s');
    expect(formatDuration(125)).toBe('2m 5s');
  });
});
```

---

## Troubleshooting Common Issues

### Issue: Progress indicator doesn't appear

**Symptoms:**
- Clicking "Process Job" does nothing
- Console shows no errors

**Solutions:**
1. Check if button click handler is bound:
   ```javascript
   // In console:
   document.querySelector('button[onclick*="processJobDetail"]')
   ```
2. Verify CSS file is loaded:
   ```javascript
   // Check for stylesheet
   Array.from(document.styleSheets).find(s => s.href?.includes('pipeline-progress.css'))
   ```

### Issue: Steps don't update

**Symptoms:**
- Progress bar moves but steps stay "Pending"
- No errors in console

**Solutions:**
1. Check layer names match exactly:
   ```javascript
   // Expected: "pain_points" (underscore)
   // Not: "pain-points" (hyphen)
   ```
2. Verify `data-layer` attributes in HTML
3. Check backend response format

### Issue: Animations are janky

**Symptoms:**
- Choppy animations
- Low FPS

**Solutions:**
1. Check for forced layout reflows:
   ```javascript
   // Chrome DevTools → Performance → Record
   // Look for "Recalculate Style" warnings
   ```
2. Verify CSS uses `transform` instead of `left/top`
3. Enable hardware acceleration (should be default)

---

## Test Completion Criteria

All tests pass when:

- [ ] Visual design matches specification
- [ ] All interactive elements work
- [ ] Responsive design works on mobile/tablet/desktop
- [ ] Accessibility requirements are met (WCAG AA)
- [ ] Performance metrics are within targets
- [ ] SSE and polling both work
- [ ] Error handling works correctly
- [ ] Cross-browser compatibility verified

---

## Next Steps After Testing

1. Create GitHub issue for any bugs found
2. Document any browser-specific quirks
3. Update this guide with new test cases
4. Consider adding automated E2E tests with Playwright
