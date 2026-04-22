# CV Upload via JavaScript Injection

Upload the CV PDF without OS file picker. Three methods in priority order.

## Method 0: Base64 Inject (works on ALL portals — no CORS, no file picker)

**Use this first for Ashby and any portal that blocks localhost fetch.**

### Step A — encode CV in Python (before browser step):
```python
import base64
with open(cv_path, 'rb') as f:
    b64 = base64.b64encode(f.read()).decode()
# b64 is the string to inject below
```

### Step B — inject via JS:
```javascript
(function injectCV(b64) {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  const blob = new Blob([bytes], { type: 'application/pdf' });
  const file = new File([blob], 'Taimoor Alam Resume.pdf', { type: 'application/pdf' });
  const dt = new DataTransfer();
  dt.items.add(file);
  const input = document.querySelector('input[type="file"][name*="cv"]')
    || document.querySelector('input[type="file"][accept*="pdf"]')
    || document.querySelector('input[type="file"]');
  if (!input) return 'NO_INPUT_FOUND';
  // FileList is read-only on some portals — use Object.defineProperty
  try {
    input.files = dt.files;
  } catch(e) {
    Object.defineProperty(input, 'files', { value: dt.files, writable: true, configurable: true });
  }
  input.dispatchEvent(new Event('change', { bubbles: true }));
  input.dispatchEvent(new Event('input',  { bubbles: true }));
  return `INJECTED: ${file.name} (${(file.size/1024).toFixed(1)} KB)`;
})('PASTE_BASE64_HERE');
```

> **Ashby note**: FileList must be set via `Object.defineProperty` — direct assignment throws. Use the try/catch above.

---

## Prerequisites (Methods 1 & 2 only)
File server running at `http://localhost:18923/resume.pdf` (started in Step 3).

## Method 1: File Input Injection via localhost (works ~80% of portals)

Use `mcp__claude-in-chrome__javascript_tool`:

```javascript
const response = await fetch('http://localhost:18923/resume.pdf');
const blob = await response.blob();
const file = new File([blob], 'Taimoor_Alam_Resume.pdf', { type: 'application/pdf' });

const input = document.querySelector('input[type="file"]')
  || document.querySelector('[data-testid*="file"]')
  || document.querySelector('[accept*="pdf"]');

if (input) {
  const dt = new DataTransfer();
  dt.items.add(file);
  input.files = dt.files;
  input.dispatchEvent(new Event('change', { bubbles: true }));
  input.dispatchEvent(new Event('input', { bubbles: true }));
  'SUCCESS';
} else {
  'NO_INPUT_FOUND';
}
```

## Method 2: Drag-and-Drop (fallback)

```javascript
const dropZone = document.querySelector('[class*="drop"]')
  || document.querySelector('[class*="upload"]')
  || document.querySelector('[data-testid*="upload"]');

if (dropZone) {
  const response = await fetch('http://localhost:18923/resume.pdf');
  const blob = await response.blob();
  const file = new File([blob], 'Taimoor_Alam_Resume.pdf', { type: 'application/pdf' });
  const dt = new DataTransfer();
  dt.items.add(file);
  dropZone.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true }));
  'SUCCESS';
} else {
  'NO_DROP_ZONE';
}
```

## Method 3: Manual (last resort)
```
Can't auto-upload CV. Please upload manually:
  {cv_path}
Type 'done' when uploaded.
```
