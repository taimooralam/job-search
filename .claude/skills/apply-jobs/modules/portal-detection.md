# Portal Detection & Playbook System

Detect portal type, match to existing playbook, or auto-generate one from page analysis. The goal: **never analyze the same portal type twice**.

## Step 1: URL-Based Detection

Match the current URL against known patterns:

| URL contains | Portal |
|-------------|--------|
| greenhouse.io, boards.greenhouse | Greenhouse |
| lever.co, jobs.lever | Lever |
| myworkdayjobs.com, workday.com | Workday |
| smartrecruiters.com | SmartRecruiters |
| ashbyhq.com | Ashby |
| bamboohr.com | BambooHR |
| linkedin.com/jobs | LinkedIn |
| indeed.com | Indeed |
| join.com | JOIN |
| personio.de, jobs.personio | Personio |
| recruitee.com | Recruitee |
| breezy.hr | Breezy |
| teamtailor.com | Teamtailor |
| workable.com | Workable |
| applytojob.com | ApplyToJob |

## Step 2: Check for Existing Playbook

Look in `data/portal-playbooks/` for a matching YAML file:

1. **Exact match**: `{portal_name}.yaml` (e.g. `ashby.yaml`)
2. **URL pattern match**: read each playbook's `url_patterns` array, check if current URL matches any pattern
3. **Custom domain match**: some companies host ATS on their own domain (e.g. `careers.acme.com` running Greenhouse). If Step 1 didn't match, scan playbooks' `url_patterns` for partial matches.

**If playbook found** → load it, follow its selectors, scripts, and known issues. Skip Step 3.

## Step 3: LinkedIn Exception

If portal is LinkedIn → **do NOT analyze**. LinkedIn Easy Apply is a well-known multi-step modal. Just proceed with the standard LinkedIn flow:
- Click "Easy Apply" button
- Fill each modal step
- Click "Next" between steps
- Pause on final "Submit" step

## Step 4: Auto-Analyze Unknown Portal

If no playbook exists and it's not LinkedIn, run a **one-time page analysis** using `mcp__claude-in-chrome__javascript_tool`:

```javascript
(function analyzePortal() {
  const result = {};

  // 1. Framework detection
  result.framework = {
    react: !!window.__REACT_DEVTOOLS_GLOBAL_HOOK__ || !!document.querySelector('[data-reactroot]'),
    vue: !!window.__VUE__,
    angular: !!window.ng,
    jquery: !!window.jQuery,
  };

  // 2. Form structure
  const forms = [...document.querySelectorAll('form')];
  result.forms = forms.map(f => ({
    id: f.id,
    action: f.action,
    method: f.method,
    fields: [...f.querySelectorAll('input,select,textarea')].map(el => ({
      tag: el.tagName,
      type: el.type,
      name: el.name,
      id: el.id,
      required: el.required,
      placeholder: el.placeholder,
      label: el.labels?.[0]?.textContent?.trim() || '',
      accept: el.accept || '',
    })),
  }));

  // 3. Apply/Submit buttons
  const buttons = [...document.querySelectorAll('button,a,[role="button"]')];
  result.apply_buttons = buttons
    .filter(b => /apply|submit|send|einreichen/i.test(b.textContent))
    .map(b => ({
      tag: b.tagName,
      text: b.textContent.trim().substring(0, 50),
      type: b.type,
      id: b.id,
      class: b.className.substring(0, 80),
      href: b.href || '',
      testid: b.getAttribute('data-testid') || '',
    }));

  // 4. File upload inputs
  result.file_inputs = [...document.querySelectorAll('input[type="file"]')].map(el => ({
    name: el.name,
    accept: el.accept,
    id: el.id,
    multiple: el.multiple,
  }));

  // 5. Drop zones
  result.drop_zones = [...document.querySelectorAll('[class*="drop"],[class*="upload"],[data-testid*="upload"]')].map(el => ({
    tag: el.tagName,
    class: el.className.substring(0, 80),
    testid: el.getAttribute('data-testid') || '',
  }));

  // 6. Login/auth detection
  result.login_required = !!(
    document.querySelector('[type="password"]') ||
    document.querySelector('[name="login"]') ||
    /sign in|log in|create account/i.test(document.body.innerText.substring(0, 2000))
  );

  // 7. Multi-step detection
  result.multi_step = !!(
    document.querySelector('[class*="step"],[class*="progress"],[class*="wizard"]') ||
    /step \d|page \d/i.test(document.body.innerText.substring(0, 2000))
  );

  // 8. Meta / title
  result.page_title = document.title;
  result.meta_generator = document.querySelector('meta[name="generator"]')?.content || '';

  return JSON.stringify(result, null, 2);
})();
```

## Step 5: Generate Playbook from Analysis

Using the analysis result, create a new playbook YAML at `data/portal-playbooks/{portal_name}.yaml`:

```yaml
portal: "{detected or URL-derived name}"
url_patterns:
  - "{url pattern generalized — e.g. 'careers.acme.com/jobs/*'}"
  - "{alternate pattern if any}"

# Detection
framework: "{react|vue|angular|jquery|vanilla}"
meta_generator: "{if any}"

# Apply flow
apply_button_selector: "{best selector from analysis}"
submit_button_selector: "{best selector from analysis}"
form_id: "{form id if any}"
login_required: true/false
multi_step: true/false

# File upload
file_upload_method: "base64_inject|localhost_fetch|drop|manual"
file_input_selector: "{name or id of file input}"
file_input_accept: "{accept attribute}"
drop_zone_selector: "{if applicable}"

# Form fields (map name → purpose)
field_map:
  "{input.name}": "first_name"
  "{input.name}": "last_name"
  "{input.name}": "email"
  "{input.name}": "phone"
  "{input.name}": "cv_upload"
  # ... all discovered fields

# React/SPA notes
input_setter_method: "native|react_setter|direct"
# native = el.value = x (works for vanilla)
# react_setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(el, x)
# direct = mcp form_input tool

# Known issues (append as discovered)
known_issues: []

# Viewport
viewport_fix: ""  # e.g. "resize to 700px for mobile layout"

last_updated: "{ISO date}"
```

## Step 6: Playbook Matching for Future Jobs

When a new job URL is opened:

1. Extract the **domain** and **path pattern** from the URL
2. For each playbook in `data/portal-playbooks/`:
   - Compare `url_patterns` against current URL
   - Compare `meta_generator` against page meta
   - Compare `framework` detection result
3. If match found with confidence > 80% → reuse that playbook
4. If partial match (same ATS but different company subdomain) → clone the playbook, adjust URL patterns

**Matching examples:**
- `jobs.acme.ashbyhq.com/o/123` → matches `ashby.yaml` via `ashbyhq.com`
- `careers.newco.com/apply` + meta_generator="Greenhouse" → matches `greenhouse.yaml`
- `apply.workday.com/newco/job/123` → matches `workday.yaml`
- `newco.com/careers/apply` + React + form structure matches lever → clone `lever.yaml`

## Playbook Evolution

After each successful application on a known portal:
- **Update** the playbook with any new field mappings, selectors, or workarounds discovered
- **Append** to `known_issues` if new quirks were encountered
- **Bump** `last_updated`

After each failed application:
- **Append** the failure reason to `known_issues`
- **Flag** if the portal has changed (e.g. "form structure changed, fields renamed")
