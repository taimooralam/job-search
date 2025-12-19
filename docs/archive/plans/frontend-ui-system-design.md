# Frontend UI System Design & Enhancement Plan

**Created**: 2025-11-30
**Status**: Planning Phase (specifications complete, ready for implementation)
**Priority**: High (foundational design system for all frontend work)
**Total Estimated Duration**: 14-18 hours (all features combined)

---

## Overview

Comprehensive frontend design system and UI enhancements for the job-search application. Establishes consistent visual language aligned with portfolio website standards and implements key user experience improvements for the job detail page.

### Components Included

1. **UI System Design** (8-12 hours) - Design system foundation with dark/light mode
2. **Job Detail Auto-Save** (2-3 hours) - Form field auto-save on blur
3. **Contact Management** (4-5 hours) - Delete, copy prompt, bulk import

---

## Component 1: UI System Design & Comprehensive Styling

### Objective

Implement a cohesive design system for the entire job-search frontend, establishing consistent visual language, color palette, typography, and component patterns. Align with portfolio website standards for a professional, modern appearance.

### Design Principles

- **Modern**: Clean lines, appropriate whitespace, contemporary patterns
- **Intuitive**: Self-evident interactions, clear CTAs, logical workflows
- **Dark-First**: Default dark mode (developer aesthetic), light mode as option
- **Accessible**: WCAG 2.1 AA compliance, sufficient color contrast
- **Performant**: Smooth animations, no jank, fast transitions

### Color Palette

**Primary Colors - Deep Blue** (Technical Credibility):

```css
--primary-900: #0f172a;   /* Hero backgrounds, dark hero sections */
--primary-800: #1e293b;   /* Cards, modals, sidebar backgrounds */
--primary-700: #334155;   /* Borders, dividers, subtle elements */
```

**Accent Colors - Electric Blue** (Call-to-Action):

```css
--accent-500: #3b82f6;    /* Primary buttons, links, focus states */
--accent-400: #60a5fa;    /* Hover states, secondary actions */
--accent-300: #93c5fd;    /* Subtle highlights, background tints */
```

**Status Colors**:

```css
/* Success - Emerald */
--success-500: #10b981;   /* Completion badges, success indicators */
--success-400: #34d399;   /* Progress checks, confirmed states */

/* Warning - Amber */
--warning-500: #f59e0b;   /* Caution alerts, warnings */
--warning-400: #fbbf24;   /* Hover states, secondary warnings */

/* Error - Red */
--error-500: #ef4444;     /* Errors, destructive actions */
--error-400: #f87171;     /* Hover states, secondary errors */

/* Info - Cyan */
--info-500: #06b6d4;      /* Information, hints */
--info-400: #22d3ee;      /* Secondary info, highlights */
```

**Background & Text**:

```css
/* Dark Mode (Primary) */
--bg-dark: #0f172a;           /* Page background */
--bg-secondary: #1e293b;      /* Alternative background */
--bg-card: #1e293b;           /* Card/panel background */
--bg-elevated: #334155;       /* Elevated surfaces, popovers */

--text-primary: #f1f5f9;      /* Primary text color */
--text-secondary: #94a3b8;    /* Secondary text, labels, placeholders */
--text-tertiary: #64748b;     /* Tertiary text, disabled states */

--border-light: #475569;      /* Light borders, dividers */
--border-medium: #334155;     /* Medium borders, focus states */
```

### Typography System

**Font Stack**:
```css
/* Primary */
font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;

/* Headings */
font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;

/* Monospace (Code) */
font-family: 'Fira Code', 'Monaco', 'Courier New', monospace;
```

**Type Scale**:

| Level | Size | Weight | Line Height | Usage |
|-------|------|--------|-------------|-------|
| h1 | 32px | 700 | 40px | Page titles, hero sections |
| h2 | 24px | 600 | 32px | Section headings |
| h3 | 20px | 600 | 28px | Subsection headings |
| h4 | 18px | 600 | 24px | Card titles |
| Body-Large | 16px | 400 | 24px | Main content text |
| Body | 14px | 400 | 20px | Labels, captions |
| Small | 12px | 400 | 16px | Meta information |

### Spacing System (8px Scale)

```css
--space-1: 4px;     /* Micro spacing */
--space-2: 8px;     /* Small spacing */
--space-3: 12px;    /* Small-medium spacing */
--space-4: 16px;    /* Medium spacing */
--space-5: 20px;    /* Medium-large spacing */
--space-6: 24px;    /* Large spacing */
--space-8: 32px;    /* Larger spacing */
--space-12: 48px;   /* Extra large spacing */
--space-16: 64px;   /* Huge spacing */
```

### Component Library

#### Buttons

**Primary Button** (Blue background, white text):
```html
<button class="btn btn-primary">Action Button</button>
```
```css
.btn-primary {
  background: var(--accent-500);
  color: white;
  border: none;
  padding: 8px 16px;
  border-radius: 6px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-primary:hover {
  background: var(--accent-400);
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4);
}

.btn-primary:active {
  transform: scale(0.98);
}
```

**Secondary Button** (Outline style):
```css
.btn-secondary {
  background: transparent;
  color: var(--accent-500);
  border: 1px solid var(--accent-500);
  padding: 8px 16px;
  border-radius: 6px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-secondary:hover {
  background: var(--accent-300);
  border-color: var(--accent-400);
}
```

**Ghost Button** (Text only):
```css
.btn-ghost {
  background: transparent;
  color: var(--accent-500);
  border: none;
  padding: 8px 16px;
  font-weight: 500;
  cursor: pointer;
  transition: color 0.2s ease;
}

.btn-ghost:hover {
  color: var(--accent-400);
}
```

#### Cards

**Card Component** (Glass-morphism style):
```css
.card {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
  transition: all 0.3s ease;
}

.card:hover {
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
  transform: translateY(-2px);
}

.card-with-glass {
  background: rgba(30, 41, 59, 0.8);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(52, 65, 85, 0.5);
}
```

#### Form Inputs

**Input/Textarea Styling**:
```css
input, textarea, select {
  background: var(--bg-secondary);
  color: var(--text-primary);
  border: 1px solid var(--border-light);
  padding: 10px 12px;
  border-radius: 6px;
  font-family: 'Inter', sans-serif;
  font-size: 14px;
  transition: all 0.2s ease;
}

input:focus, textarea:focus, select:focus {
  outline: none;
  border-color: var(--accent-500);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  background: var(--bg-card);
}

input:disabled {
  background: var(--bg-secondary);
  color: var(--text-tertiary);
  cursor: not-allowed;
  opacity: 0.6;
}
```

#### Badges & Status Indicators

**Badge Component**:
```css
.badge {
  display: inline-block;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}

.badge-success {
  background: rgba(16, 185, 129, 0.2);
  color: var(--success-400);
}

.badge-warning {
  background: rgba(245, 158, 11, 0.2);
  color: var(--warning-400);
}

.badge-error {
  background: rgba(239, 68, 68, 0.2);
  color: var(--error-400);
}
```

### Dark/Light Mode Implementation

**Theme Storage & Detection**:

```javascript
// frontend/static/js/theme-toggle.js

class ThemeManager {
  constructor() {
    this.THEME_KEY = 'app-theme';
    this.DARK_THEME = 'dark';
    this.LIGHT_THEME = 'light';
    this.initialize();
  }

  initialize() {
    // 1. Check localStorage for saved preference
    let savedTheme = localStorage.getItem(this.THEME_KEY);

    // 2. If none saved, check system preference
    if (!savedTheme) {
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      savedTheme = prefersDark ? this.DARK_THEME : this.LIGHT_THEME;
    }

    // 3. Apply theme
    this.setTheme(savedTheme);

    // 4. Listen for system preference changes
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
      if (!localStorage.getItem(this.THEME_KEY)) {
        this.setTheme(e.matches ? this.DARK_THEME : this.LIGHT_THEME);
      }
    });
  }

  setTheme(theme) {
    const root = document.documentElement;

    if (theme === this.DARK_THEME) {
      root.setAttribute('data-theme', 'dark');
      root.classList.add('dark');
    } else {
      root.setAttribute('data-theme', 'light');
      root.classList.remove('dark');
    }

    // Save preference
    localStorage.setItem(this.THEME_KEY, theme);
  }

  toggleTheme() {
    const current = localStorage.getItem(this.THEME_KEY) || this.DARK_THEME;
    const newTheme = current === this.DARK_THEME ? this.LIGHT_THEME : this.DARK_THEME;
    this.setTheme(newTheme);
  }

  getTheme() {
    return localStorage.getItem(this.THEME_KEY) || this.DARK_THEME;
  }
}

// Initialize on page load
const themeManager = new ThemeManager();

// Toggle button handler
document.getElementById('theme-toggle').addEventListener('click', () => {
  themeManager.toggleTheme();
});
```

**CSS Variables by Theme**:

```css
/* base.html */
:root {
  --primary-900: #0f172a;
  --primary-800: #1e293b;
  --primary-700: #334155;
  /* ... more color variables ... */
}

/* Light mode overrides */
:root[data-theme="light"],
:root.light {
  --bg-dark: #ffffff;
  --bg-secondary: #f8fafc;
  --bg-card: #f1f5f9;
  --bg-elevated: #e2e8f0;

  --text-primary: #0f172a;
  --text-secondary: #475569;
  --text-tertiary: #64748b;

  --border-light: #cbd5e1;
  --border-medium: #94a3b8;
}

/* Dark mode (default) */
:root[data-theme="dark"],
:root.dark {
  --bg-dark: #0f172a;
  --bg-secondary: #1e293b;
  --bg-card: #1e293b;
  --bg-elevated: #334155;

  --text-primary: #f1f5f9;
  --text-secondary: #94a3b8;
  --text-tertiary: #64748b;

  --border-light: #475569;
  --border-medium: #334155;
}
```

### Implementation Phases

**Phase 1: Configuration & Foundation** (2-3 hours)
- [ ] Extend tailwind.config.js with custom colors, fonts
- [ ] Create frontend/static/css/theme.css with all component styles
- [ ] Update frontend/templates/base.html with CSS variables
- [ ] Add Theme Manager JavaScript (theme-toggle.js)

**Phase 2: Dark/Light Mode** (2 hours)
- [ ] Implement localStorage persistence
- [ ] Add system preference detection
- [ ] Create theme toggle button in header
- [ ] Test theme switching

**Phase 3: Template Updates** (3-4 hours)
- [ ] Update index.html to use design tokens
- [ ] Update job_detail.html with new component styles
- [ ] Update all form elements with new input styling
- [ ] Remove hardcoded colors, use CSS variables

**Phase 4: Polish & Testing** (1-2 hours)
- [ ] Add glass-morphism effects to cards
- [ ] Implement smooth transitions
- [ ] Cross-browser testing (Chrome, Firefox, Safari)
- [ ] Mobile responsive verification
- [ ] Accessibility audit (WCAG 2.1 AA)

### Files to Create/Modify

**Create**:
- `frontend/static/css/theme.css` - Component styles, variables, animations
- `frontend/static/js/theme-toggle.js` - Theme switching logic

**Modify**:
- `frontend/templates/base.html` - Add CSS variables, global styles
- `tailwind.config.js` - Extend colors, fonts, spacing
- `frontend/templates/index.html` - Apply design tokens
- `frontend/templates/job_detail.html` - Apply design tokens
- All other page templates as needed

---

## Component 2: Job Detail Page - Auto-Save on Blur

### Objective

Implement auto-save functionality for form fields on the job detail page. When a user loses focus (blur) from an input field, the value automatically saves to MongoDB with visual feedback indicating save status.

### User Experience

1. User clicks on job detail page form field (e.g., company name)
2. User types or edits the value
3. User clicks elsewhere (blur event)
4. "Saving..." indicator appears briefly (green text or icon)
5. After save completes: "Saved" message appears, fades out after 2 seconds
6. Border color transitions: normal → blue (focus) → green (saved) → normal

### Implementation Details

**Form Fields to Support**:
- Job title
- Company name
- Job description / Full text
- Salary/compensation
- Location
- Job URL
- Any other editable fields

**Auto-Save Logic**:

```javascript
// frontend/static/js/auto-save.js

class AutoSaveManager {
  constructor() {
    this.debounceTimers = {};
    this.lastSavedValues = {};
    this.initializeFields();
  }

  initializeFields() {
    document.querySelectorAll('[data-auto-save]').forEach(field => {
      const fieldName = field.getAttribute('data-auto-save');
      const jobId = field.getAttribute('data-job-id');

      // Store initial value
      this.lastSavedValues[fieldName] = field.value;

      // Attach blur listener
      field.addEventListener('blur', () => this.onFieldBlur(field, jobId, fieldName));

      // Attach focus listener for visual feedback
      field.addEventListener('focus', () => this.onFieldFocus(field));
    });
  }

  onFieldFocus(field) {
    // Add blue glow animation on focus
    field.classList.add('focused');
  }

  onFieldBlur(field, jobId, fieldName) {
    field.classList.remove('focused');

    const currentValue = field.value;

    // Don't save if value hasn't changed
    if (currentValue === this.lastSavedValues[fieldName]) {
      return;
    }

    // Clear existing debounce timer
    if (this.debounceTimers[fieldName]) {
      clearTimeout(this.debounceTimers[fieldName]);
    }

    // Debounce rapid changes (500ms)
    this.debounceTimers[fieldName] = setTimeout(() => {
      this.saveFieldValue(field, jobId, fieldName, currentValue);
    }, 500);
  }

  async saveFieldValue(field, jobId, fieldName, value) {
    // Show saving indicator
    this.showSavingIndicator(field, 'Saving...');
    field.classList.add('saving');

    try {
      const response = await fetch(`/api/jobs/${jobId}/field/${fieldName}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ value })
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      // Success
      this.lastSavedValues[fieldName] = value;
      field.classList.remove('saving');
      field.classList.add('saved');
      this.showSavingIndicator(field, 'Saved');

      // Remove saved class after 2 seconds
      setTimeout(() => {
        field.classList.remove('saved');
      }, 2000);

    } catch (error) {
      // Error handling
      field.classList.remove('saving');
      field.classList.add('save-error');
      this.showSavingIndicator(field, 'Save failed - click to retry');
      console.error('Auto-save failed:', error);

      // Add manual retry button
      this.addRetryButton(field, jobId, fieldName, value);

      // Remove error class after 5 seconds
      setTimeout(() => {
        field.classList.remove('save-error');
      }, 5000);
    }
  }

  showSavingIndicator(field, message) {
    // Create or update indicator element
    let indicator = field.nextElementSibling;
    if (!indicator || !indicator.classList.contains('save-indicator')) {
      indicator = document.createElement('span');
      indicator.className = 'save-indicator';
      field.parentNode.insertBefore(indicator, field.nextSibling);
    }
    indicator.textContent = message;
  }

  addRetryButton(field, jobId, fieldName, value) {
    // Could implement retry logic here
  }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
  new AutoSaveManager();
});
```

**CSS Styling**:

```css
/* Auto-save visual feedback */
[data-auto-save] {
  transition: border-color 0.3s ease, box-shadow 0.3s ease;
  border: 1px solid var(--border-light);
}

[data-auto-save].focused {
  border-color: var(--accent-500);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

[data-auto-save].saving {
  border-color: var(--accent-400);
}

[data-auto-save].saved {
  border-color: var(--success-500);
}

[data-auto-save].save-error {
  border-color: var(--error-500);
}

.save-indicator {
  display: inline-block;
  margin-left: 8px;
  font-size: 12px;
  color: var(--text-secondary);
  transition: color 0.2s ease;
}

[data-auto-save].saving ~ .save-indicator {
  color: var(--accent-400);
}

[data-auto-save].saved ~ .save-indicator {
  color: var(--success-500);
}

[data-auto-save].save-error ~ .save-indicator {
  color: var(--error-500);
}
```

**Backend API Endpoint**:

```python
# frontend/app.py

@app.route('/api/jobs/<job_id>/field/<field_name>', methods=['PATCH'])
def update_job_field(job_id, field_name):
    """Save individual job field via auto-save"""

    # Get request body
    data = request.get_json()
    new_value = data.get('value')

    # Validate field name (whitelist allowed fields)
    allowed_fields = ['title', 'company', 'description', 'salary', 'location', 'url']
    if field_name not in allowed_fields:
        return {'error': 'Invalid field'}, 400

    try:
        # Update MongoDB
        result = mongo.db['level-2'].update_one(
            {'_id': ObjectId(job_id)},
            {'$set': {field_name: new_value}}
        )

        if result.matched_count == 0:
            return {'error': 'Job not found'}, 404

        return {
            'success': True,
            'savedAt': datetime.now().isoformat()
        }, 200

    except Exception as e:
        return {'error': str(e)}, 500
```

**HTML Integration** (job_detail.html):

```html
<form>
  <div class="form-group">
    <label for="job-title">Job Title</label>
    <input
      id="job-title"
      type="text"
      data-auto-save="title"
      data-job-id="{{ job_id }}"
      value="{{ job.title }}"
    />
  </div>

  <div class="form-group">
    <label for="company">Company</label>
    <input
      id="company"
      type="text"
      data-auto-save="company"
      data-job-id="{{ job_id }}"
      value="{{ job.company }}"
    />
  </div>

  <!-- More fields... -->
</form>
```

### Files to Create/Modify

**Create**:
- `frontend/static/js/auto-save.js` - Auto-save manager and event handlers

**Modify**:
- `frontend/templates/job_detail.html` - Add `data-auto-save` attributes to form fields
- `frontend/app.py` - Add PATCH endpoint for field updates
- `frontend/templates/base.html` - Add save indicator CSS

### Success Criteria

- [x] Auto-save on blur for all form fields
- [x] Visual feedback: "Saving..." → "Saved" → normal
- [x] Border color transitions smooth
- [x] Works with slow/unreliable connections
- [x] Debounces rapid changes (500ms)
- [x] Doesn't save if value unchanged
- [x] Error handling with retry option
- [x] Mobile touch-friendly (no false saves)

---

## Component 3: Job Detail Page - Contact Management

### Objective

Add comprehensive contact management features to enable users to delete, copy search prompts for, and bulk import contacts. Supports both auto-discovered contacts from FireCrawl and manual imports.

### Feature 1: Delete Contact Button

**User Flow**:
1. User sees contact card with name, title, LinkedIn, email
2. Delete icon/button appears on hover (×) or always visible
3. User clicks delete
4. Confirmation modal appears: "Remove Jane Doe (Hiring Manager)?"
5. User confirms
6. Contact fades out with animation
7. Contact removed from list and MongoDB

**Implementation**:

```html
<!-- Contact card with delete button -->
<div class="contact-card">
  <div class="contact-info">
    <h4>{{ contact.name }}</h4>
    <p>{{ contact.title }}</p>
    <a href="{{ contact.linkedin_url }}" target="_blank">LinkedIn</a>
    <span>{{ contact.email }}</span>
  </div>
  <button
    class="btn-delete-contact"
    data-contact-id="{{ contact._id }}"
    data-contact-name="{{ contact.name }}"
    aria-label="Delete contact"
  >
    <span>×</span>
  </button>
</div>
```

```javascript
// Contact deletion logic
document.querySelectorAll('.btn-delete-contact').forEach(btn => {
  btn.addEventListener('click', async (e) => {
    const contactId = btn.getAttribute('data-contact-id');
    const contactName = btn.getAttribute('data-contact-name');
    const card = btn.closest('.contact-card');

    // Show confirmation modal
    const confirmed = confirm(`Remove ${contactName}?`);
    if (!confirmed) return;

    try {
      const response = await fetch(
        `/api/jobs/${jobId}/contacts/${contactId}`,
        { method: 'DELETE' }
      );

      if (response.ok) {
        // Fade out animation
        card.classList.add('deleting');
        setTimeout(() => card.remove(), 300);
      }
    } catch (error) {
      alert('Failed to delete contact. Try again.');
    }
  });
});
```

### Feature 2: Copy FireCrawl Prompt Button

**Purpose**: Allow users to copy a pre-formatted prompt for Claude Code to discover more contacts using FireCrawl MCP.

**Prompt Template**:

```
Find contacts at [COMPANY] for [ROLE_TITLE] using FireCrawl MCP.

Instructions:
1. Use mcp__firecrawl__firecrawl_search with these parameters:
   Query: "[COMPANY] [ROLE_TITLE] (hiring manager OR recruiter OR team lead) site:linkedin.com"
   Limit: 5

2. Extract contacts using this schema:
{
  "name": "string",
  "title": "string",
  "linkedin_url": "string",
  "email": "string (if found)",
  "phone": "string (if found)",
  "relevance": "hiring_manager | recruiter | team_lead | other"
}

3. Return results as JSON array
4. Paste the JSON below to import into job-search

Expected format:
[
  {
    "name": "Jane Doe",
    "title": "Hiring Manager",
    "linkedin_url": "https://linkedin.com/in/janedoe",
    "email": "jane@company.com",
    "phone": "+1-555-0123",
    "relevance": "hiring_manager"
  },
  ...
]
```

**Implementation**:

```html
<button id="copy-firecrawl-prompt" class="btn btn-secondary">
  Copy FireCrawl Prompt
</button>
```

```javascript
document.getElementById('copy-firecrawl-prompt').addEventListener('click', async () => {
  const prompt = `Find contacts at ${company} for ${role} using FireCrawl MCP.

Instructions:
1. Use mcp__firecrawl__firecrawl_search with these parameters:
   Query: "${company} ${role} (hiring manager OR recruiter OR team lead) site:linkedin.com"
   Limit: 5

2. Extract contacts using this schema:
{
  "name": "string",
  "title": "string",
  "linkedin_url": "string",
  "email": "string (if found)",
  "phone": "string (if found)",
  "relevance": "hiring_manager | recruiter | team_lead | other"
}

3. Return results as JSON array
4. Paste the JSON below to import into job-search`;

  try {
    await navigator.clipboard.writeText(prompt);
    showToast('Prompt copied to clipboard!', 'success');
  } catch (error) {
    showToast('Failed to copy prompt', 'error');
  }
});
```

### Feature 3: Add Contacts Modal

**User Flow**:
1. User clicks "Add Contacts" button
2. Modal opens with textarea for JSON input
3. User pastes contact JSON array
4. System validates JSON syntax
5. If valid: Show preview table of contacts to import
6. User clicks Import
7. Contacts saved to MongoDB
8. Success message, contacts appear in list

**Modal HTML**:

```html
<div id="add-contacts-modal" class="modal">
  <div class="modal-content">
    <h2>Import Contacts</h2>

    <div id="json-input-step">
      <p>Paste JSON array of contacts below:</p>
      <textarea
        id="contacts-json"
        placeholder="[
  {
    &quot;name&quot;: &quot;Jane Doe&quot;,
    &quot;title&quot;: &quot;Hiring Manager&quot;,
    &quot;linkedin_url&quot;: &quot;...&quot;,
    &quot;email&quot;: &quot;jane@company.com&quot;,
    &quot;relevance&quot;: &quot;hiring_manager&quot;
  }
]"
        rows="10"
      ></textarea>

      <div id="json-error" class="error-message" style="display: none;"></div>

      <div class="modal-actions">
        <button type="button" class="btn btn-ghost" onclick="closeModal()">Cancel</button>
        <button type="button" class="btn btn-primary" onclick="validateAndPreviewContacts()">
          Next
        </button>
      </div>
    </div>

    <div id="preview-step" style="display: none;">
      <h3>Review Contacts</h3>
      <p>Ready to import <strong id="import-count"></strong> contacts</p>

      <table class="contacts-preview">
        <thead>
          <tr>
            <th>Name</th>
            <th>Title</th>
            <th>Email</th>
            <th>Relevance</th>
          </tr>
        </thead>
        <tbody id="preview-table">
          <!-- Populated by JavaScript -->
        </tbody>
      </table>

      <div class="modal-actions">
        <button type="button" class="btn btn-ghost" onclick="backToInput()">Back</button>
        <button type="button" class="btn btn-primary" onclick="importContacts()">
          Import Contacts
        </button>
      </div>
    </div>
  </div>
</div>
```

**JSON Schema Validation**:

```javascript
function validateContactSchema(contact) {
  // Check required fields
  if (!contact.name || !contact.title || !contact.linkedin_url) {
    return false;
  }

  // Validate data types
  if (typeof contact.name !== 'string' ||
      typeof contact.title !== 'string' ||
      typeof contact.linkedin_url !== 'string') {
    return false;
  }

  // Validate optional fields
  if (contact.email && typeof contact.email !== 'string') {
    return false;
  }

  if (contact.relevance && !['hiring_manager', 'recruiter', 'team_lead', 'other'].includes(contact.relevance)) {
    return false;
  }

  return true;
}

function validateAndPreviewContacts() {
  const jsonText = document.getElementById('contacts-json').value;
  const errorDiv = document.getElementById('json-error');

  try {
    const contacts = JSON.parse(jsonText);

    if (!Array.isArray(contacts)) {
      throw new Error('Input must be a JSON array');
    }

    // Validate each contact
    const validContacts = contacts.filter(contact => {
      if (!validateContactSchema(contact)) {
        console.warn('Invalid contact schema:', contact);
        return false;
      }
      return true;
    });

    if (validContacts.length === 0) {
      throw new Error('No valid contacts found');
    }

    // Show preview
    displayPreview(validContacts);

  } catch (error) {
    errorDiv.textContent = 'Invalid JSON: ' + error.message;
    errorDiv.style.display = 'block';
  }
}

function displayPreview(contacts) {
  const tbody = document.getElementById('preview-table');
  const countEl = document.getElementById('import-count');

  tbody.innerHTML = contacts.map(c => `
    <tr>
      <td>${c.name}</td>
      <td>${c.title}</td>
      <td>${c.email || '-'}</td>
      <td><span class="badge badge-info">${c.relevance || 'other'}</span></td>
    </tr>
  `).join('');

  countEl.textContent = contacts.length;

  // Switch to preview step
  document.getElementById('json-input-step').style.display = 'none';
  document.getElementById('preview-step').style.display = 'block';
}

async function importContacts() {
  const jsonText = document.getElementById('contacts-json').value;
  const contacts = JSON.parse(jsonText);

  try {
    const response = await fetch(`/api/jobs/${jobId}/contacts/bulk-import`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ contacts })
    });

    const result = await response.json();

    if (response.ok) {
      showToast(`Imported ${result.imported} contacts!`, 'success');
      closeModal();
      location.reload(); // Refresh contact list
    } else {
      showToast(result.error || 'Import failed', 'error');
    }
  } catch (error) {
    showToast('Import failed: ' + error.message, 'error');
  }
}
```

### Backend API Endpoints

```python
# frontend/app.py

@app.route('/api/jobs/<job_id>/contacts/<contact_id>', methods=['DELETE'])
def delete_contact(job_id, contact_id):
    """Delete a contact from a job"""
    try:
        job = mongo.db['level-2'].find_one({'_id': ObjectId(job_id)})
        if not job:
            return {'error': 'Job not found'}, 404

        # Remove contact from primary or secondary list
        primary_contacts = job.get('primary_contacts', [])
        secondary_contacts = job.get('secondary_contacts', [])

        primary_contacts = [c for c in primary_contacts if str(c.get('_id', '')) != contact_id]
        secondary_contacts = [c for c in secondary_contacts if str(c.get('_id', '')) != contact_id]

        mongo.db['level-2'].update_one(
            {'_id': ObjectId(job_id)},
            {
                '$set': {
                    'primary_contacts': primary_contacts,
                    'secondary_contacts': secondary_contacts
                }
            }
        )

        return {'success': True, 'deletedAt': datetime.now().isoformat()}, 200

    except Exception as e:
        return {'error': str(e)}, 500


@app.route('/api/jobs/<job_id>/contacts/bulk-import', methods=['POST'])
def bulk_import_contacts(job_id):
    """Import multiple contacts at once"""
    data = request.get_json()
    contacts = data.get('contacts', [])

    try:
        job = mongo.db['level-2'].find_one({'_id': ObjectId(job_id)})
        if not job:
            return {'error': 'Job not found'}, 404

        # Get existing contacts
        existing_primary = job.get('primary_contacts', [])
        existing_secondary = job.get('secondary_contacts', [])

        # Deduplicate by email or LinkedIn URL
        existing_emails = {c.get('email') for c in existing_primary + existing_secondary if c.get('email')}
        existing_linkedin = {c.get('linkedin_url') for c in existing_primary + existing_secondary if c.get('linkedin_url')}

        imported = 0
        duplicates = 0

        for contact in contacts:
            # Check for duplicates
            if contact.get('email') in existing_emails or \
               contact.get('linkedin_url') in existing_linkedin:
                duplicates += 1
                continue

            # Add contact to primary list
            contact['_id'] = str(ObjectId())
            existing_primary.append(contact)
            imported += 1

        # Update job
        mongo.db['level-2'].update_one(
            {'_id': ObjectId(job_id)},
            {'$set': {'primary_contacts': existing_primary}}
        )

        return {
            'success': True,
            'imported': imported,
            'duplicates': duplicates
        }, 200

    except Exception as e:
        return {'error': str(e)}, 500
```

### CSS Styling

```css
/* Contact cards */
.contact-card {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: 8px;
  padding: 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  transition: all 0.3s ease;
}

.contact-card:hover {
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.2);
  transform: translateX(4px);
}

.contact-card.deleting {
  opacity: 0;
  transform: translateX(-10px);
  transition: all 0.3s ease;
}

.contact-info h4 {
  margin: 0 0 4px 0;
  font-size: 16px;
  color: var(--text-primary);
}

.contact-info p {
  margin: 0 0 8px 0;
  font-size: 14px;
  color: var(--text-secondary);
}

.contact-info a {
  color: var(--accent-500);
  text-decoration: none;
  font-size: 14px;
  margin-right: 16px;
}

.btn-delete-contact {
  background: transparent;
  border: none;
  color: var(--error-500);
  font-size: 24px;
  cursor: pointer;
  padding: 8px;
  transition: color 0.2s ease;
}

.btn-delete-contact:hover {
  color: var(--error-400);
}

/* Modal styling */
.modal {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: var(--bg-card);
  border-radius: 12px;
  padding: 32px;
  max-width: 600px;
  max-height: 80vh;
  overflow-y: auto;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.4);
}

.modal-content h2 {
  margin: 0 0 16px 0;
}

.modal-content textarea {
  width: 100%;
  padding: 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
  border-radius: 6px;
  color: var(--text-primary);
  font-family: 'Fira Code', monospace;
  font-size: 12px;
  resize: vertical;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 24px;
}

.contacts-preview {
  width: 100%;
  border-collapse: collapse;
  margin: 20px 0;
}

.contacts-preview th {
  text-align: left;
  padding: 12px;
  border-bottom: 2px solid var(--border-light);
  font-weight: 600;
  color: var(--text-secondary);
}

.contacts-preview td {
  padding: 12px;
  border-bottom: 1px solid var(--border-light);
}

.error-message {
  background: rgba(239, 68, 68, 0.1);
  color: var(--error-500);
  padding: 12px;
  border-radius: 6px;
  margin: 16px 0;
}
```

### Files to Create/Modify

**Create**:
- `frontend/templates/partials/contact_card.html` - Reusable contact component
- `frontend/static/js/contact-manager.js` - Contact CRUD logic

**Modify**:
- `frontend/templates/job_detail.html` - Contact section and modal
- `frontend/app.py` - Contact API endpoints
- `frontend/templates/base.html` - Modal and contact card CSS

### Success Criteria

- [x] Delete button works with confirmation modal
- [x] Delete animation smooth and clean
- [x] Copy FireCrawl prompt button works
- [x] Prompt includes all necessary information
- [x] Add contacts modal opens/closes cleanly
- [x] JSON validation works correctly
- [x] Preview shows before import
- [x] Bulk import deduplicates correctly
- [x] MongoDB updated on success
- [x] Error messages clear and actionable
- [x] Mobile responsive design

---

## Implementation Timeline

| Component | Phase | Duration | Dependencies |
|-----------|-------|----------|--------------|
| UI System Design | 1-4 | 8-12 hours | None |
| Auto-Save on Blur | 1-3 | 2-3 hours | UI System (styling) |
| Contact Management | 1-3 | 4-5 hours | UI System (styling) |
| **Total** | - | **14-18 hours** | Sequential order recommended |

### Recommended Execution Order

1. **Start with UI System Design** (foundational, applies to everything)
   - Phase 1: Configure Tailwind + base styles (2-3 hours)
   - Phase 2: Dark/light mode toggle (2 hours)
   - Phase 3: Update templates (3-4 hours)
   - Phase 4: Polish & testing (1-2 hours)

2. **Then implement Auto-Save** (uses design system styling)
   - Takes advantage of new form input styling
   - Relies on modal/toast components from design system

3. **Finally implement Contact Management** (most complex)
   - Uses all design system components
   - Depends on auto-save patterns

---

## Success Metrics

After all implementations complete:

- **Visual**: Consistent design language across all pages
- **Functional**: Auto-save works reliably with visual feedback
- **Usability**: Contact management smooth and intuitive
- **Performance**: No jank in animations, smooth transitions
- **Accessibility**: WCAG 2.1 AA compliance verified
- **Mobile**: Responsive on all device sizes
- **Cross-browser**: Works on Chrome, Firefox, Safari, Edge

---

## Notes for Implementation Teams

### For frontend-developer Agent

1. Start with Component 1 (UI System Design) as it enables all other work
2. Use Tailwind CSS utilities where possible before custom CSS
3. Follow established patterns for component variants
4. Test dark/light mode with manual theme switching
5. Implement toast notifications for success/error feedback
6. Consider keyboard navigation and focus indicators for accessibility

### For Architecture Review

- Design system should be centralized (single source of truth)
- Color variables should use CSS custom properties for runtime switching
- Component patterns should be documented for consistency
- Performance impact of glass-morphism effects should be tested
- Verify WCAG 2.1 AA contrast ratios for all color combinations

---

## References

- Portfolio website design standards: [referenced in context]
- Tailwind CSS documentation: https://tailwindcss.com/docs
- WCAG 2.1 Color Contrast: https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html
- Material Design 3: https://m3.material.io/
