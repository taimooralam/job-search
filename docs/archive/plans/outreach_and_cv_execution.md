# Outreach & CV Execution: Complete Implementation Plan

**Document:** plans/outreach_and_cv_execution.md
**Version:** 1.0
**Date:** 2025-11-26
**Status:** Planning

---

## Executive Summary

This document outlines the implementation plan for 4 interconnected modules that enhance the job intelligence pipeline's outreach and CV management capabilities:

1. **Enable FireCrawl Contact Discovery** - Real contact discovery using SEO-style queries
2. **Fix CV HTML Editing** - Make in-browser CV editing functional
3. **Add Cover Letter Editing** - Build editing UI/API for cover letters
4. **Enhance CV.html Generator** - Create richer, more styled HTML CVs

**Estimated Total Effort:** 8-12 hours
**Risk Level:** Medium (mostly UI/integration work with existing infrastructure)

---

## Module 1: Enable FireCrawl Contact Discovery

### 1.1 Current State Analysis

**Status:** DISABLED by default (`DISABLE_FIRECRAWL_OUTREACH=true`)

**What Exists:**
- Complete 4-source discovery implementation (team pages, LinkedIn, leadership, Crunchbase)
- SEO-style query templates already defined
- Proper metadata extraction from search results (not markdown)
- Fallback to 4+4 synthetic role-based contacts
- Comprehensive test suite (885 lines in `tests/unit/test_layer5_people_mapper.py`)

**Why It's Disabled:**
- Original queries were too verbose/conversational
- Response handling expected markdown content
- No adaptive retry strategy

**Key Finding:** The code has ALREADY been refactored to use Option A (SEO-style queries + metadata extraction). It just needs to be enabled and tested.

### 1.2 Implementation Steps

#### Step 1.1: Enable Feature Flag
```bash
# .env file
DISABLE_FIRECRAWL_OUTREACH=false
```

**File:** `.env` (development), VPS `.env` (production)

#### Step 1.2: Verify Query Templates
**File:** `src/layer5/people_mapper.py` (lines 82-88)

Confirm templates are SEO-optimized:
```python
QUERY_TEMPLATES = {
    "recruiters": 'site:linkedin.com/in "{company}" {department} recruiter',
    "leadership": '"{company}" "VP {department}" OR "Director {department}" LinkedIn',
    "hiring_manager": '"{company}" "{title}" hiring manager LinkedIn',
    "talent_acquisition": '"{company}" talent acquisition recruiter LinkedIn',
}
```

#### Step 1.3: Test with Real Company
```bash
# Integration test
python scripts/run_pipeline.py --job-id <test-job-with-known-company>

# Check Layer 5 output
# Should see: "FireCrawl discovery enabled"
# Should see: Real LinkedIn profile URLs (not synthetic)
```

#### Step 1.4: Monitor and Log Query Performance
Add logging to track which queries succeed:
```python
# In _search_linkedin_contacts() around line 469
logger.info(f"[FireCrawl] Query: {query}")
logger.info(f"[FireCrawl] Results: {len(results)} contacts found")
```

### 1.3 Test Cases

| Test ID | Description | Input | Expected Output | Pass Criteria |
|---------|-------------|-------|-----------------|---------------|
| FC-01 | Enable discovery | `DISABLE_FIRECRAWL_OUTREACH=false` | Layer 5 uses FireCrawl | No synthetic contacts generated |
| FC-02 | Query execution | Company: "Atlassian" | LinkedIn profiles returned | 2+ real contacts with URLs |
| FC-03 | Metadata extraction | Search result with title | Name, role, URL parsed | All 3 fields populated |
| FC-04 | Deduplication | Duplicate contacts from 4 sources | Unique contacts only | No duplicate names |
| FC-05 | Fallback trigger | FireCrawl API error | Synthetic contacts generated | 4 primary + 4 secondary |
| FC-06 | Rate limiting | 10+ jobs in sequence | All complete without 429 | No FireCrawl errors |

### 1.4 Success Criteria

- [ ] FireCrawl discovery runs without errors for 5 consecutive jobs
- [ ] At least 3/8 contacts have real LinkedIn URLs (not company/people)
- [ ] Query execution time < 30 seconds for all 4 sources
- [ ] Fallback works correctly when FireCrawl fails
- [ ] Existing tests pass: `pytest tests/unit/test_layer5_people_mapper.py -v`

### 1.5 Failure Scenarios & Mitigation

| Failure Mode | Detection | Mitigation |
|--------------|-----------|------------|
| FireCrawl API down | HTTP 5xx errors | Auto-fallback to synthetic contacts |
| Rate limiting (429) | Too Many Requests error | Exponential backoff (already implemented) |
| Poor query results | 0 contacts returned | Try alternate query templates |
| Invalid LinkedIn URLs | URL doesn't match pattern | Validate URL format before saving |
| Timeout | >60s response time | 30s timeout with fallback |

### 1.6 Risk Assessment

**Risk Level:** LOW

**Rationale:**
- Infrastructure is 95% complete
- Comprehensive fallback exists
- 885-line test suite covers edge cases
- Only configuration change needed to enable

---

## Module 2: Fix CV HTML Editing

### 2.1 Current State Analysis

**What Exists:**
- `HTMLCVGenerator` class generates CV.html with `contenteditable="true"` attributes
- Frontend has Edit/Save/PDF buttons and JavaScript functions
- Backend API endpoints: GET, PUT, POST (PDF), GET (download)
- Playwright PDF generation

**What's Broken:**
- **iframe cross-origin access** - `iframe.contentDocument` returns null
- CV displayed in iframe from `/api/jobs/{id}/cv` endpoint
- JavaScript can't access iframe DOM due to same-origin policy

### 2.2 Root Cause

```javascript
// job_detail.html line 964-970
if (cvIframeDoc) {  // cvIframeDoc is NULL!
    const editableElements = cvIframeDoc.querySelectorAll('[contenteditable]');
    // This never executes
}
```

**Problem:** Browser security prevents parent page from accessing iframe content when loaded from different origin/path.

### 2.3 Implementation Steps

#### Step 2.1: Remove iframe, Embed CV Directly

**File:** `frontend/templates/job_detail.html`

**Current (broken):**
```html
<iframe id="cv-iframe" src="/api/jobs/{{ job._id }}/cv"></iframe>
```

**New (working):**
```html
<div id="cv-container" class="cv-preview">
    {% if job.cv_html_content %}
        {{ job.cv_html_content | safe }}
    {% else %}
        <p class="text-gray-500">No CV generated yet</p>
    {% endif %}
</div>
```

#### Step 2.2: Update Backend to Provide CV HTML Content

**File:** `frontend/app.py` (job_detail route, line 688)

Add CV content loading:
```python
# After loading job from MongoDB
cv_html_content = None
if job.get("company") and job.get("title"):
    company_clean = job["company"].replace(" ", "_").replace("/", "_")
    title_clean = job["title"].replace(" ", "_").replace("/", "_")
    cv_path = Path("../applications") / company_clean / title_clean / "CV.html"
    if cv_path.exists():
        cv_html_content = cv_path.read_text()

serialized_job["cv_html_content"] = cv_html_content
```

#### Step 2.3: Update JavaScript Edit Functions

**File:** `frontend/templates/job_detail.html` (lines 950-1021)

Replace iframe-based editing with direct DOM manipulation:
```javascript
function toggleCVEdit() {
    cvEditMode = !cvEditMode;
    const cvContainer = document.getElementById('cv-container');
    const editableElements = cvContainer.querySelectorAll('[contenteditable]');

    if (cvEditMode) {
        editableElements.forEach(el => el.setAttribute('contenteditable', 'true'));
        // Show save button, change edit button text
    } else {
        editableElements.forEach(el => el.setAttribute('contenteditable', 'false'));
        // Hide save button, reset edit button
    }
}

async function saveCVChanges() {
    const cvContainer = document.getElementById('cv-container');
    const htmlContent = cvContainer.innerHTML;

    const response = await fetch(`/api/jobs/${jobId}/cv`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ html_content: htmlContent })
    });
    // Handle response
}
```

#### Step 2.4: Add Scoped CSS for Embedded CV

**File:** `frontend/templates/job_detail.html`

Add CSS to isolate CV styles from page styles:
```css
.cv-preview {
    background: white;
    padding: 2rem;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    max-height: 800px;
    overflow-y: auto;
}

.cv-preview [contenteditable="true"]:hover {
    background: #edf2f7;
    outline: 1px dashed #2b6cb0;
}

.cv-preview [contenteditable="true"]:focus {
    background: #e6fffa;
    outline: 2px solid #38b2ac;
}
```

### 2.4 Test Cases

| Test ID | Description | Input | Expected Output | Pass Criteria |
|---------|-------------|-------|-----------------|---------------|
| CV-01 | CV displays | Job with CV.html | CV content visible | All sections rendered |
| CV-02 | Edit mode toggle | Click "Edit CV" | Elements become editable | Hover/focus styles appear |
| CV-03 | Text editing | Click and type in name | Text changes | New text visible |
| CV-04 | Save changes | Edit + click Save | PUT request sent | 200 response, file updated |
| CV-05 | Cancel editing | Edit + click Cancel | Changes discarded | Original text restored |
| CV-06 | PDF generation | Click "Generate PDF" | Playwright creates PDF | PDF file downloadable |
| CV-07 | No CV state | Job without CV | "No CV" message | No errors thrown |

### 2.5 Success Criteria

- [ ] CV displays without iframe
- [ ] Edit mode enables contenteditable on all elements
- [ ] Changes persist after save
- [ ] PDF generation still works
- [ ] No CORS or security errors in console
- [ ] Works in Chrome, Firefox, Safari

### 2.6 Failure Scenarios & Mitigation

| Failure Mode | Detection | Mitigation |
|--------------|-----------|------------|
| CSS conflicts | CV layout broken | Scope all CV styles with `.cv-preview` prefix |
| Save fails | API returns error | Show error toast, keep edit mode |
| Large CV | Page slow to load | Add loading spinner, lazy load |
| PDF generation fails | Playwright error | Show retry button, log error |

### 2.7 Risk Assessment

**Risk Level:** MEDIUM

**Rationale:**
- Requires template restructuring
- CSS isolation needed
- But: Backend API already works, just frontend changes

---

## Module 3: Add Cover Letter Editing

### 3.1 Current State Analysis

**What Exists:**
- `CoverLetterGenerator` creates cover_letter.txt with 6+ validation gates
- Cover letter stored in MongoDB (`cover_letter` field)
- Cover letter saved to disk (`applications/.../cover_letter.txt`)

**What's Missing:**
- NO display section in job_detail.html
- NO editing UI
- `cover_letter` NOT in editable fields whitelist (app.py line 442)

### 3.2 Implementation Steps

#### Step 3.1: Add Cover Letter to Backend Editable Fields

**File:** `frontend/app.py` (line 442-444)

```python
editable_fields = [
    "status", "remarks", "notes", "priority",
    "company", "title", "location", "score", "url", "jobUrl",
    "cover_letter"  # ADD THIS
]
```

#### Step 3.2: Add Cover Letter Display Section

**File:** `frontend/templates/job_detail.html`

Add after CV section (around line 209):
```html
<!-- Cover Letter Section -->
{% if job.cover_letter %}
<div class="mb-6">
    <div class="flex justify-between items-center mb-3">
        <h2 class="text-sm font-semibold text-gray-700 uppercase tracking-wide">
            <svg class="inline-block h-4 w-4 mr-1 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
            </svg>
            Cover Letter
        </h2>
        <div class="flex gap-2">
            <button id="edit-cl-btn" onclick="toggleCoverLetterEdit()"
                    class="inline-flex items-center px-3 py-1 text-xs font-medium rounded-md text-purple-700 bg-purple-50 hover:bg-purple-100 border border-purple-200 transition">
                <svg class="h-3 w-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/>
                </svg>
                <span id="edit-cl-text">Edit</span>
            </button>
            <button id="save-cl-btn" onclick="saveCoverLetterChanges()"
                    class="hidden inline-flex items-center px-3 py-1 text-xs font-medium rounded-md text-white bg-purple-600 hover:bg-purple-700 transition">
                <svg class="h-3 w-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
                </svg>
                Save
            </button>
        </div>
    </div>

    <!-- Display Mode -->
    <div id="cl-display" class="p-4 bg-gray-50 rounded-lg border border-gray-200">
        <pre id="cl-text" class="whitespace-pre-wrap font-sans text-sm text-gray-800 leading-relaxed">{{ job.cover_letter }}</pre>
    </div>

    <!-- Edit Mode (hidden by default) -->
    <textarea id="cl-textarea"
              class="hidden w-full h-64 p-4 border border-purple-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-purple-500 text-sm"
              placeholder="Enter cover letter text...">{{ job.cover_letter }}</textarea>

    <!-- Validation Warnings (shown after save) -->
    <div id="cl-warnings" class="hidden mt-2 p-3 bg-yellow-50 border border-yellow-200 rounded-lg text-sm text-yellow-800"></div>
</div>
{% endif %}
```

#### Step 3.3: Add JavaScript Functions

**File:** `frontend/templates/job_detail.html` (in `{% block extra_js %}`)

```javascript
let clEditMode = false;

function toggleCoverLetterEdit() {
    clEditMode = !clEditMode;

    const editBtn = document.getElementById('edit-cl-btn');
    const editText = document.getElementById('edit-cl-text');
    const saveBtn = document.getElementById('save-cl-btn');
    const displayDiv = document.getElementById('cl-display');
    const textArea = document.getElementById('cl-textarea');
    const warningsDiv = document.getElementById('cl-warnings');

    if (clEditMode) {
        // Enter edit mode
        editText.textContent = 'Cancel';
        editBtn.classList.remove('text-purple-700', 'bg-purple-50', 'border-purple-200');
        editBtn.classList.add('text-red-700', 'bg-red-50', 'border-red-200');
        saveBtn.classList.remove('hidden');
        displayDiv.classList.add('hidden');
        textArea.classList.remove('hidden');
        warningsDiv.classList.add('hidden');
        textArea.focus();
    } else {
        // Exit edit mode (cancel)
        editText.textContent = 'Edit';
        editBtn.classList.remove('text-red-700', 'bg-red-50', 'border-red-200');
        editBtn.classList.add('text-purple-700', 'bg-purple-50', 'border-purple-200');
        saveBtn.classList.add('hidden');
        displayDiv.classList.remove('hidden');
        textArea.classList.add('hidden');
        // Reset textarea to original value
        textArea.value = document.getElementById('cl-text').textContent;
    }
}

async function saveCoverLetterChanges() {
    const textArea = document.getElementById('cl-textarea');
    const newText = textArea.value.trim();

    if (!newText) {
        showToast('Cover letter cannot be empty', 'error');
        return;
    }

    showToast('Saving cover letter...', 'info');

    try {
        const response = await fetch(`/api/jobs/${jobId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ cover_letter: newText })
        });

        const result = await response.json();

        if (result.success) {
            // Update display
            document.getElementById('cl-text').textContent = newText;
            showToast('Cover letter saved');

            // Validate and show warnings
            validateCoverLetter(newText);

            // Exit edit mode
            toggleCoverLetterEdit();
        } else {
            showToast(result.error || 'Failed to save', 'error');
        }
    } catch (err) {
        showToast('Save failed: ' + err.message, 'error');
    }
}

function validateCoverLetter(text) {
    const warnings = [];
    const words = text.split(/\s+/).length;

    // Word count check
    if (words < 180) warnings.push('Cover letter is short (' + words + ' words, recommended: 180-420)');
    if (words > 420) warnings.push('Cover letter is long (' + words + ' words, recommended: 180-420)');

    // Metrics check
    if (!/\d+%|\d+x|\$\d+|\d+\s*(years?|months?|days?|hours?)/i.test(text)) {
        warnings.push('No quantified metrics found (add percentages, multipliers, or dollar amounts)');
    }

    // Calendly check
    if (!text.includes('calendly.com/taimooralam')) {
        warnings.push('Missing Calendly link (required for call-to-action)');
    }

    // Boilerplate check
    const boilerplate = ['excited to apply', 'dream job', 'perfect fit', 'passionate about', 'eager to'];
    const found = boilerplate.filter(phrase => text.toLowerCase().includes(phrase));
    if (found.length > 2) {
        warnings.push('Contains generic phrases: ' + found.join(', '));
    }

    // Show warnings
    const warningsDiv = document.getElementById('cl-warnings');
    if (warnings.length > 0) {
        warningsDiv.innerHTML = '<strong>Validation Warnings:</strong><ul class="list-disc ml-4 mt-1">' +
            warnings.map(w => '<li>' + w + '</li>').join('') + '</ul>';
        warningsDiv.classList.remove('hidden');
    }
}
```

### 3.4 Test Cases

| Test ID | Description | Input | Expected Output | Pass Criteria |
|---------|-------------|-------|-----------------|---------------|
| CL-01 | Display cover letter | Job with cover_letter | Text visible | Full text rendered |
| CL-02 | Edit mode toggle | Click "Edit" | Textarea appears | Display hides, textarea shows |
| CL-03 | Text editing | Type in textarea | Text changes | New text visible |
| CL-04 | Save changes | Click Save | PUT request sent | 200 response, MongoDB updated |
| CL-05 | Cancel editing | Click Cancel | Changes discarded | Original text restored |
| CL-06 | Validation warnings | Save short letter | Warning shown | "short" warning appears |
| CL-07 | No cover letter | Job without cover_letter | Section hidden | No errors |
| CL-08 | Empty save blocked | Save empty text | Error toast | Save prevented |

### 3.5 Success Criteria

- [ ] Cover letter displays for jobs that have one
- [ ] Edit/Save flow works correctly
- [ ] Changes persist in MongoDB
- [ ] Validation warnings appear for quality issues
- [ ] Section hidden when no cover letter exists

### 3.6 Risk Assessment

**Risk Level:** LOW

**Rationale:**
- Simple UI addition
- Uses existing PUT API with whitelist change
- No complex state management

---

## Module 4: Enhance CV.html Generator

### 4.1 Current State Analysis

**Current Output:**
- Basic HTML structure (minimal when no STARs available)
- Simple CSS styling
- `contenteditable` attributes present
- 1,184 bytes for minimal CV (too small)

**What's Needed:**
- Richer visual design
- More sections (Skills, Languages, Certifications)
- Better typography
- Print-optimized layout
- Consistent styling with/without STARs

### 4.2 Implementation Steps

#### Step 4.1: Create Rich HTML Template

**File:** `src/layer6/html_cv_generator.py`

Update `_build_html_cv()` method (lines 103-380) with enhanced template:

```python
def _build_html_cv(self, state: JobState, selected_stars: List[dict]) -> str:
    """Build rich HTML CV with professional styling."""

    # Extract data from state
    profile = state.get("candidate_profile", "")
    job_title = state.get("title", "")
    company = state.get("company", "")

    # Parse profile for structured data
    name = self._extract_name(profile)
    contact = self._extract_contact(profile)
    summary = self._extract_summary(profile, state)
    skills = self._extract_skills(profile, state)
    education = self._extract_education(profile)
    certifications = self._extract_certifications(profile)
    languages = self._extract_languages(profile)

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CV - {name} - {job_title}</title>
    <style>
        /* Reset & Base */
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            font-size: 11pt;
            line-height: 1.5;
            color: #1a202c;
            background: #f7fafc;
            padding: 0;
        }}

        /* Container */
        .cv-container {{
            max-width: 850px;
            margin: 2rem auto;
            background: white;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            padding: 3rem;
        }}

        /* Header */
        .cv-header {{
            text-align: center;
            border-bottom: 3px solid #2b6cb0;
            padding-bottom: 1.5rem;
            margin-bottom: 2rem;
        }}
        .cv-name {{
            font-size: 2.5rem;
            font-weight: 700;
            color: #1a365d;
            letter-spacing: -0.5px;
        }}
        .cv-tagline {{
            font-size: 1.1rem;
            color: #4a5568;
            margin-top: 0.5rem;
        }}
        .cv-contact {{
            display: flex;
            justify-content: center;
            gap: 1.5rem;
            margin-top: 1rem;
            font-size: 0.9rem;
            color: #718096;
        }}
        .cv-contact a {{
            color: #2b6cb0;
            text-decoration: none;
        }}

        /* Sections */
        .cv-section {{
            margin-bottom: 2rem;
        }}
        .cv-section-title {{
            font-size: 1.1rem;
            font-weight: 600;
            color: #2b6cb0;
            text-transform: uppercase;
            letter-spacing: 1px;
            border-bottom: 1px solid #e2e8f0;
            padding-bottom: 0.5rem;
            margin-bottom: 1rem;
        }}

        /* Summary */
        .cv-summary {{
            font-size: 0.95rem;
            color: #4a5568;
            line-height: 1.7;
        }}

        /* Skills Grid */
        .cv-skills-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 1rem;
        }}
        .cv-skill-category {{
            background: #f7fafc;
            padding: 1rem;
            border-radius: 8px;
            border-left: 3px solid #2b6cb0;
        }}
        .cv-skill-category h4 {{
            font-size: 0.85rem;
            font-weight: 600;
            color: #2d3748;
            margin-bottom: 0.5rem;
        }}
        .cv-skill-category ul {{
            list-style: none;
            font-size: 0.85rem;
            color: #4a5568;
        }}

        /* Experience */
        .cv-experience-item {{
            margin-bottom: 1.5rem;
            padding-left: 1rem;
            border-left: 2px solid #e2e8f0;
        }}
        .cv-experience-header {{
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            margin-bottom: 0.5rem;
        }}
        .cv-role {{
            font-weight: 600;
            color: #2d3748;
        }}
        .cv-company {{
            color: #2b6cb0;
        }}
        .cv-period {{
            font-size: 0.85rem;
            color: #718096;
        }}
        .cv-bullets {{
            margin-left: 1rem;
        }}
        .cv-bullets li {{
            margin-bottom: 0.5rem;
            color: #4a5568;
            font-size: 0.9rem;
        }}

        /* Education & Certs */
        .cv-education-item {{
            margin-bottom: 0.75rem;
        }}
        .cv-degree {{
            font-weight: 600;
            color: #2d3748;
        }}
        .cv-institution {{
            color: #718096;
            font-size: 0.9rem;
        }}

        /* Languages */
        .cv-languages {{
            display: flex;
            gap: 1.5rem;
            flex-wrap: wrap;
        }}
        .cv-language {{
            background: #edf2f7;
            padding: 0.5rem 1rem;
            border-radius: 20px;
            font-size: 0.85rem;
        }}

        /* Editable Styles */
        [contenteditable="true"]:hover {{
            background: #edf2f7;
            outline: 1px dashed #2b6cb0;
            border-radius: 2px;
        }}
        [contenteditable="true"]:focus {{
            background: #e6fffa;
            outline: 2px solid #38b2ac;
            border-radius: 2px;
        }}

        /* Print Styles */
        @media print {{
            body {{ background: white; padding: 0; }}
            .cv-container {{ box-shadow: none; margin: 0; padding: 1.5rem; }}
            [contenteditable]:hover, [contenteditable]:focus {{
                background: none; outline: none;
            }}
        }}

        /* Metadata (hidden) */
        .cv-metadata {{
            display: none;
        }}
    </style>
</head>
<body>
    <div class="cv-container">
        <!-- Header -->
        <header class="cv-header">
            <h1 class="cv-name" contenteditable="false">{name}</h1>
            <p class="cv-tagline" contenteditable="false">{job_title} | Strategic Technology Leadership</p>
            <div class="cv-contact" contenteditable="false">
                {contact}
            </div>
        </header>

        <!-- Summary -->
        <section class="cv-section">
            <h2 class="cv-section-title">Professional Summary</h2>
            <p class="cv-summary" contenteditable="false">{summary}</p>
        </section>

        <!-- Skills -->
        <section class="cv-section">
            <h2 class="cv-section-title">Core Competencies</h2>
            <div class="cv-skills-grid">
                {skills}
            </div>
        </section>

        <!-- Experience -->
        <section class="cv-section">
            <h2 class="cv-section-title">Professional Experience</h2>
            {self._build_experience_section(selected_stars)}
        </section>

        <!-- Education -->
        <section class="cv-section">
            <h2 class="cv-section-title">Education</h2>
            <div contenteditable="false">{education}</div>
        </section>

        <!-- Certifications -->
        {f'''
        <section class="cv-section">
            <h2 class="cv-section-title">Certifications</h2>
            <div contenteditable="false">{certifications}</div>
        </section>
        ''' if certifications else ''}

        <!-- Languages -->
        {f'''
        <section class="cv-section">
            <h2 class="cv-section-title">Languages</h2>
            <div class="cv-languages">{languages}</div>
        </section>
        ''' if languages else ''}

        <!-- Hidden Metadata -->
        <div class="cv-metadata">
            <span data-job-id="{state.get('job_id', '')}"></span>
            <span data-company="{company}"></span>
            <span data-role="{job_title}"></span>
            <span data-generated="{datetime.utcnow().isoformat()}"></span>
        </div>
    </div>
</body>
</html>'''

    return html
```

#### Step 4.2: Add Helper Methods for Data Extraction

**File:** `src/layer6/html_cv_generator.py`

```python
def _extract_name(self, profile: str) -> str:
    """Extract candidate name from profile."""
    lines = profile.split('\n')
    for line in lines[:5]:
        if line.startswith('# '):
            return line[2:].strip()
    return "Candidate Name"

def _extract_skills(self, profile: str, state: JobState) -> str:
    """Build skills grid HTML from profile and job requirements."""
    # Parse skills from profile
    # Cross-reference with job requirements
    # Return HTML for skills grid
    pass

def _build_experience_section(self, stars: List[dict]) -> str:
    """Build professional experience from STAR records."""
    if not stars:
        return '<p class="text-gray-500">Experience details available upon request.</p>'

    html = ""
    for star in stars:
        html += f'''
        <div class="cv-experience-item">
            <div class="cv-experience-header">
                <span>
                    <span class="cv-role" contenteditable="false">{star.get('role', 'Role')}</span>
                    <span class="cv-company" contenteditable="false">— {star.get('company', 'Company')}</span>
                </span>
                <span class="cv-period" contenteditable="false">{star.get('period', '')}</span>
            </div>
            <ul class="cv-bullets">
                {self._build_bullets(star)}
            </ul>
        </div>
        '''
    return html

def _build_bullets(self, star: dict) -> str:
    """Build achievement bullets from STAR record."""
    bullets = []
    for action in star.get('actions', []):
        bullet = f'<li contenteditable="false">{action}</li>'
        bullets.append(bullet)
    for result in star.get('results', []):
        bullet = f'<li contenteditable="false">{result}</li>'
        bullets.append(bullet)
    return '\n'.join(bullets[:5])  # Max 5 bullets per role
```

### 4.3 Test Cases

| Test ID | Description | Input | Expected Output | Pass Criteria |
|---------|-------------|-------|-----------------|---------------|
| HTML-01 | Full CV generation | Job with 3+ STARs | Rich HTML CV | All sections present |
| HTML-02 | Minimal CV | Job with no STARs | Basic CV | Name/contact/summary |
| HTML-03 | Skills extraction | Profile with skills | Skills grid | 3-column layout |
| HTML-04 | Print preview | Browser print | Clean layout | No edit indicators |
| HTML-05 | File size | Generated CV | Reasonable size | 15-30KB typical |
| HTML-06 | Contenteditable | All editable elements | Attributes present | Can edit in browser |
| HTML-07 | Mobile responsive | Small viewport | Readable layout | No horizontal scroll |

### 4.4 Success Criteria

- [ ] HTML CV is visually professional
- [ ] All sections render correctly
- [ ] Skills grid shows relevant competencies
- [ ] Experience section uses STAR data when available
- [ ] Print output is clean and professional
- [ ] File size is 15-30KB for typical CV
- [ ] All contenteditable attributes work

### 4.5 Risk Assessment

**Risk Level:** MEDIUM

**Rationale:**
- Significant template rewrite
- Profile parsing may have edge cases
- CSS complexity for print/screen/mobile

---

## Implementation Order

### Recommended Sequence

1. **Module 1: Enable FireCrawl** (1-2 hours)
   - Mostly configuration
   - Low risk, high value
   - Can be tested independently

2. **Module 3: Cover Letter Editing** (2-3 hours)
   - Simple UI addition
   - Uses existing API infrastructure
   - No dependencies on other modules

3. **Module 2: Fix CV Editing** (2-3 hours)
   - Medium complexity
   - Requires template restructuring
   - Dependent on Module 4 for best results

4. **Module 4: Enhance CV Generator** (3-4 hours)
   - Most complex
   - Improves all CV-related features
   - Best done last for incremental testing

### Dependency Graph

```
Module 1 (FireCrawl)     ──── Independent
         │
         ▼
Module 3 (CL Editing)    ──── Independent
         │
         ▼
Module 4 (CV Generator)  ──── Enhances Module 2
         │
         ▼
Module 2 (CV Editing)    ──── Depends on Module 4
```

---

## Testing Strategy

### Unit Tests

| Module | Test File | Test Count |
|--------|-----------|------------|
| 1 | `tests/unit/test_layer5_people_mapper.py` | 30+ existing |
| 2 | `tests/frontend/test_cv_editing.py` | 10 new |
| 3 | `tests/frontend/test_cover_letter_editing.py` | 8 new |
| 4 | `tests/unit/test_html_cv_generator.py` | 15 new |

### Integration Tests

```bash
# Full pipeline with FireCrawl enabled
DISABLE_FIRECRAWL_OUTREACH=false python scripts/run_pipeline.py --job-id <test-job>

# Verify all outputs
ls -la applications/<company>/<role>/
# Should have: CV.html, CV.md, cover_letter.txt, dossier.txt, contacts_outreach.txt
```

### Manual Testing Checklist

- [ ] Enable FireCrawl, run pipeline, verify real contacts
- [ ] Open job detail page, verify CV displays
- [ ] Click Edit CV, modify text, save, verify persists
- [ ] Scroll to cover letter, edit, save, verify persists
- [ ] Generate PDF, verify download works
- [ ] Test on mobile viewport
- [ ] Test print preview

---

## Rollback Plan

If any module causes issues:

### Module 1 Rollback
```bash
# In .env
DISABLE_FIRECRAWL_OUTREACH=true
# Immediate fallback to synthetic contacts
```

### Module 2/3/4 Rollback
```bash
# Revert frontend changes
git checkout HEAD^ -- frontend/templates/job_detail.html

# Revert backend changes
git checkout HEAD^ -- frontend/app.py

# Revert generator changes
git checkout HEAD^ -- src/layer6/html_cv_generator.py
```

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| FireCrawl success rate | >60% real contacts | Log analysis |
| CV editing completion | 100% of edits save | Error logs |
| Cover letter editing | 100% of edits save | Error logs |
| CV file size | 15-30KB | File size check |
| PDF generation | 100% success | Error logs |
| Page load time | <3s | Browser dev tools |
| Test coverage | >80% | pytest-cov |

---

## Timeline

| Day | Tasks |
|-----|-------|
| 1 | Module 1 (FireCrawl) + Module 3 (CL Editing) |
| 2 | Module 4 (CV Generator) + Module 2 (CV Editing) |
| 3 | Testing + Bug fixes + Documentation |

---

## Appendix: File References

### Critical Files

| File | Purpose | Modules |
|------|---------|---------|
| `src/layer5/people_mapper.py` | Contact discovery | 1 |
| `src/layer6/html_cv_generator.py` | CV HTML generation | 4 |
| `src/layer6/cover_letter_generator.py` | Cover letter generation | 3 |
| `frontend/templates/job_detail.html` | Job detail UI | 2, 3 |
| `frontend/app.py` | Backend API | 2, 3 |
| `src/common/config.py` | Configuration flags | 1 |

### Test Files

| File | Purpose |
|------|---------|
| `tests/unit/test_layer5_people_mapper.py` | FireCrawl tests |
| `tests/frontend/test_cv_editing.py` | CV editing tests (NEW) |
| `tests/frontend/test_cover_letter_editing.py` | CL editing tests (NEW) |
| `tests/unit/test_html_cv_generator.py` | CV generator tests (NEW) |

---

**Document End**
