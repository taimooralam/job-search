# Design System Summary

**Created**: 2025-11-27
**Version**: 1.0
**Location**: `/Users/ala0001t/pers/projects/job-search/frontend/templates/base.html`

## Quick Reference

### Design Tokens (CSS Custom Properties)

#### Colors
```css
/* Primary (Indigo) */
--color-primary-50 to --color-primary-950

/* Semantic */
--color-success-500, --color-warning-500, --color-error-500, --color-info-500

/* Neutral */
--color-gray-50 to --color-gray-950
```

#### Typography
```css
--font-sans: 'Inter', system-fonts
--text-xs (12px) to --text-4xl (36px)
--font-normal (400) to --font-bold (700)
--line-height-tight (1.25), normal (1.5), relaxed (1.75)
```

#### Spacing
```css
--space-1 (4px) to --space-20 (80px)
/* Based on 4px grid */
```

#### Shadows
```css
--shadow-subtle, sm, md, lg, xl, 2xl, inner
```

#### Transitions
```css
--transition-fast (150ms), base (200ms), slow (300ms)
```

## Component Classes

### Buttons
```html
<!-- Primary Button -->
<button class="btn btn-primary btn-md">Submit</button>

<!-- Secondary Button -->
<button class="btn btn-secondary btn-sm">Cancel</button>

<!-- Danger Button -->
<button class="btn btn-danger btn-md">Delete</button>

<!-- Success Button -->
<button class="btn btn-success btn-lg">Confirm</button>

<!-- Ghost Button -->
<button class="btn btn-ghost btn-md">More</button>
```

### Cards
```html
<!-- Basic Card -->
<div class="card">
  <div class="card-body">Content</div>
</div>

<!-- Interactive Card with Hover -->
<div class="card card-hover">
  <div class="card-header">
    <h3>Title</h3>
  </div>
  <div class="card-body">
    <p>Content</p>
  </div>
  <div class="card-footer">
    <button class="btn btn-primary btn-sm">Action</button>
  </div>
</div>
```

### Forms
```html
<label class="form-label">Name</label>
<input type="text" class="form-input" placeholder="Enter name">

<label class="form-label">Status</label>
<select class="form-select">
  <option>Option 1</option>
  <option>Option 2</option>
</select>
```

### Badges
```html
<span class="badge badge-success">Active</span>
<span class="badge badge-error">Failed</span>
<span class="badge badge-warning">Pending</span>
<span class="badge badge-gray">Draft</span>
```

### Modals
```html
<div id="my-modal" class="hidden modal">
  <div class="modal-backdrop" onclick="closeModal()"></div>
  <div class="modal-content">
    <div class="card-header">Modal Title</div>
    <div class="card-body">Modal content</div>
    <div class="card-footer">
      <button class="btn btn-ghost btn-md">Cancel</button>
      <button class="btn btn-primary btn-md">Confirm</button>
    </div>
  </div>
</div>
```

### Loading States
```html
<!-- Spinner -->
<div class="spinner"></div>
<div class="spinner spinner-sm"></div>
<div class="spinner spinner-lg"></div>

<!-- Skeleton Loader -->
<div class="skeleton h-4 w-32"></div>
```

### Toasts
```javascript
// JavaScript function
showToast('Success message', 'success');
showToast('Error message', 'error');
showToast('Info message', 'info');
```

## Usage Guidelines

### Color Usage
- **Primary (Indigo)**: Primary actions, links, brand elements
- **Success (Green)**: Confirmations, successful states
- **Warning (Orange)**: Caution states, warnings
- **Error (Red)**: Errors, destructive actions, failures
- **Info (Blue)**: Informational messages, neutral actions
- **Gray**: Text, borders, backgrounds, disabled states

### Typography Hierarchy
```
Headings:
- h1: --text-4xl (36px) + --font-bold
- h2: --text-2xl (24px) + --font-semibold
- h3: --text-xl (20px) + --font-semibold
- h4: --text-lg (18px) + --font-medium

Body:
- Large: --text-base (16px)
- Normal: --text-sm (14px)
- Small: --text-xs (12px)
```

### Spacing Patterns
```
Tight spacing (cards, forms): --space-3 to --space-6
Medium spacing (sections): --space-6 to --space-12
Large spacing (page sections): --space-12 to --space-20
```

### Shadow Usage
```
Subtle: Form inputs, subtle hover effects
SM: Cards, dropdowns
MD: Elevated cards, modals
LG: Popovers, tooltips
XL/2XL: Modals, overlays (dramatic elevation)
```

## Accessibility Checklist

- ✅ Color contrast ≥ 4.5:1 for text
- ✅ Focus indicators visible (indigo ring)
- ✅ Keyboard navigation support
- ✅ Touch targets ≥ 44x44px
- ✅ Semantic HTML elements
- ✅ ARIA labels where needed

## Browser Support

- Chrome/Edge: 88+
- Firefox: 85+
- Safari: 14+
- Mobile browsers: iOS 14+, Android Chrome 88+

## Migration Guide (For Existing Code)

### Old → New

#### Buttons
```html
<!-- Old -->
<button class="px-4 py-2 bg-indigo-600 text-white rounded-md">Submit</button>

<!-- New -->
<button class="btn btn-primary btn-md">Submit</button>
```

#### Cards
```html
<!-- Old -->
<div class="bg-white rounded-lg shadow p-6">Content</div>

<!-- New -->
<div class="card">
  <div class="card-body">Content</div>
</div>
```

#### Forms
```html
<!-- Old -->
<input type="text" class="border border-gray-300 rounded-md px-3 py-2">

<!-- New -->
<input type="text" class="form-input">
```

## Examples in Context

### Job Card
```html
<div class="card card-hover cursor-pointer">
  <div class="card-body">
    <div class="flex justify-between items-start mb-3">
      <h3 class="text-lg font-semibold text-gray-900">Senior Frontend Developer</h3>
      <span class="badge badge-primary">New</span>
    </div>
    <p class="text-sm text-gray-600 mb-3">Company Name · Location</p>
    <div class="flex gap-2">
      <span class="badge badge-gray">Remote</span>
      <span class="badge badge-success">Match: 95%</span>
    </div>
  </div>
  <div class="card-footer flex justify-between items-center">
    <span class="text-xs text-gray-500">Added 2 hours ago</span>
    <button class="btn btn-primary btn-sm">View Details</button>
  </div>
</div>
```

### Action Toolbar
```html
<div class="card">
  <div class="card-body flex items-center justify-between">
    <div class="flex items-center gap-3">
      <span class="text-sm text-gray-600">
        <span class="font-semibold">3</span> jobs selected
      </span>
    </div>
    <div class="flex gap-2">
      <button class="btn btn-ghost btn-sm">Export</button>
      <button class="btn btn-secondary btn-sm">Mark Applied</button>
      <button class="btn btn-danger btn-sm">Delete</button>
    </div>
  </div>
</div>
```

## Design Inspiration Sources

- **Linear**: Clean minimal UI, subtle animations, excellent typography
- **Notion**: Soft shadows, rounded corners, information hierarchy
- **Stripe Dashboard**: Professional, trustworthy, clear data presentation
- **Vercel**: Modern monochrome with accent colors, excellent spacing
- **Figma**: Colorful accents, clean layouts, intuitive interactions

## Maintenance

### Adding New Colors
```css
:root {
  --color-custom-500: #yourcolor;
  --color-custom-600: #darkershade;
}
```

### Adding New Components
1. Add component styles in base.html after existing components
2. Follow BEM-like naming: `.component-variant`
3. Use design tokens (CSS variables) for values
4. Include hover/focus/disabled states
5. Add to this summary document

### Testing New Components
1. Test in Chrome, Firefox, Safari
2. Test on mobile devices
3. Validate WCAG 2.1 AA compliance
4. Check keyboard navigation
5. Test with screen readers (if interactive)

---

**For Questions**: See `ui-ux-design-refresh-report.md` for detailed implementation notes.
