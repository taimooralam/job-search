# CV Rich Text Editor - Architecture & Implementation Plan

## Executive Summary

Build a professional CV rich text editor as a collapsible side panel with:
- TipTap editor (ProseMirror-based) for rich text editing
- Google Fonts integration for professional typography
- Auto-save to MongoDB with visual indicator
- Exact state restoration (content + styles) across sessions
- Client-side PDF export

---

## 1. Requirements Specification

### 1.1 UI/UX Requirements

| Feature | Description | Priority |
|---------|-------------|----------|
| Side Panel | Notion-style slide-out panel from right | P0 |
| Collapse/Expand | Panel can be collapsed or expanded to full screen | P0 |
| Floating Toolbar | Slidable rich text formatting toolbar | P0 |
| Save Indicator | Shows "Saved" after 3s of inactivity | P0 |
| PDF Export | Download CV as PDF to local machine | P0 |

### 1.2 Text Formatting Requirements

| Feature | Implementation | Priority |
|---------|----------------|----------|
| Bold | `Ctrl+B` / toolbar button | P0 |
| Italic | `Ctrl+I` / toolbar button | P0 |
| Underline | `Ctrl+U` / toolbar button | P0 |
| Bullet Points | Unordered lists | P0 |
| Numbered Lists | Ordered lists | P1 |
| Tabbing/Indentation | Tab key / indent buttons | P0 |
| Font Family | Google Fonts dropdown (10-15 fonts) | P0 |
| Font Size | Size dropdown (8-24pt) | P0 |
| Ruler | Margin/indent controls | P1 |
| Line Height | Spacing control | P1 |
| Text Alignment | Left/Center/Right/Justify | P1 |

### 1.3 Data Requirements

| Requirement | Details |
|-------------|---------|
| State Persistence | Content + all formatting stored in MongoDB |
| State Restoration | Exact recreation on page reload |
| Auto-save | After 3 seconds of inactivity |
| Version History | Optional: keep last 5 versions |

### 1.4 Performance Requirements

| Metric | Target |
|--------|--------|
| Memory Usage | < 100MB for typical CV |
| Auto-save Latency | < 500ms |
| Initial Load | < 2 seconds |
| No Browser Crashes | Stable with documents up to 10 pages |

---

## 2. Technology Stack

### 2.1 Editor: TipTap v2

**Why TipTap:**
- Built on ProseMirror (battle-tested, used by NY Times, Atlassian)
- Outputs JSON (perfect for MongoDB storage)
- Highly extensible with modular extensions
- Excellent React/vanilla JS support
- 30k+ GitHub stars, active maintenance
- Memory efficient, no crashes on large documents

**Extensions Required:**
```javascript
// Core
@tiptap/core
@tiptap/starter-kit  // Basic formatting
@tiptap/extension-underline
@tiptap/extension-text-align
@tiptap/extension-font-family
@tiptap/extension-text-style
@tiptap/extension-bullet-list
@tiptap/extension-ordered-list

// Custom
FontSize extension (custom)
Ruler extension (custom)
Indent extension (custom)
```

### 2.2 Fonts: Comprehensive Google Fonts Library

**60+ Professional Free Fonts organized by category:**

```javascript
const PROFESSIONAL_FONTS = {
  // SANS-SERIF - Modern, Clean, Professional
  sansSerif: [
    { name: 'Inter', weights: [400, 500, 600, 700], description: 'Modern, highly readable' },
    { name: 'Roboto', weights: [300, 400, 500, 700], description: 'Google standard' },
    { name: 'Open Sans', weights: [400, 600, 700], description: 'Friendly, neutral' },
    { name: 'Lato', weights: [400, 700, 900], description: 'Warm, professional' },
    { name: 'Source Sans Pro', weights: [400, 600, 700], description: 'Adobe designed' },
    { name: 'Montserrat', weights: [400, 500, 600, 700], description: 'Geometric, modern' },
    { name: 'Poppins', weights: [400, 500, 600, 700], description: 'Geometric, friendly' },
    { name: 'Nunito', weights: [400, 600, 700], description: 'Rounded, approachable' },
    { name: 'Nunito Sans', weights: [400, 600, 700], description: 'Clean sans-serif' },
    { name: 'Work Sans', weights: [400, 500, 600, 700], description: 'Optimized for screens' },
    { name: 'Raleway', weights: [400, 500, 600, 700], description: 'Elegant, thin strokes' },
    { name: 'Rubik', weights: [400, 500, 600, 700], description: 'Slightly rounded' },
    { name: 'Quicksand', weights: [400, 500, 600, 700], description: 'Rounded, geometric' },
    { name: 'Mukta', weights: [400, 500, 600, 700], description: 'Devanagari + Latin' },
    { name: 'Karla', weights: [400, 500, 600, 700], description: 'Grotesque sans' },
    { name: 'Barlow', weights: [400, 500, 600, 700], description: 'Slightly rounded' },
    { name: 'IBM Plex Sans', weights: [400, 500, 600, 700], description: 'IBM corporate' },
    { name: 'DM Sans', weights: [400, 500, 700], description: 'Low-contrast geometric' },
    { name: 'Manrope', weights: [400, 500, 600, 700], description: 'Semi-rounded modern' },
    { name: 'Public Sans', weights: [400, 500, 600, 700], description: 'US government standard' },
    { name: 'Outfit', weights: [400, 500, 600, 700], description: 'Geometric sans' },
    { name: 'Plus Jakarta Sans', weights: [400, 500, 600, 700], description: 'Modern geometric' },
    { name: 'Figtree', weights: [400, 500, 600, 700], description: 'Friendly geometric' },
    { name: 'Lexend', weights: [400, 500, 600, 700], description: 'Readability optimized' },
  ],

  // SERIF - Traditional, Elegant, Authoritative
  serif: [
    { name: 'Merriweather', weights: [400, 700], description: 'Screen-optimized serif' },
    { name: 'Playfair Display', weights: [400, 500, 600, 700], description: 'High contrast, elegant' },
    { name: 'Lora', weights: [400, 500, 600, 700], description: 'Contemporary serif' },
    { name: 'PT Serif', weights: [400, 700], description: 'Transitional serif' },
    { name: 'Source Serif Pro', weights: [400, 600, 700], description: 'Adobe companion' },
    { name: 'Libre Baskerville', weights: [400, 700], description: 'Classic book serif' },
    { name: 'Crimson Text', weights: [400, 600, 700], description: 'Old-style book face' },
    { name: 'EB Garamond', weights: [400, 500, 600, 700], description: 'Claude Garamond revival' },
    { name: 'Cormorant Garamond', weights: [400, 500, 600, 700], description: 'Display Garamond' },
    { name: 'Spectral', weights: [400, 500, 600, 700], description: 'Screen-first serif' },
    { name: 'Bitter', weights: [400, 500, 600, 700], description: 'Slab serif' },
    { name: 'Vollkorn', weights: [400, 500, 600, 700], description: 'Quiet body text' },
    { name: 'Cardo', weights: [400, 700], description: 'Academic serif' },
    { name: 'Noto Serif', weights: [400, 700], description: 'Google universal' },
    { name: 'IBM Plex Serif', weights: [400, 500, 600, 700], description: 'IBM corporate serif' },
    { name: 'Domine', weights: [400, 500, 600, 700], description: 'High-contrast text' },
    { name: 'Neuton', weights: [400, 700], description: 'Modern Dutch' },
    { name: 'Libre Caslon Text', weights: [400, 700], description: 'William Caslon revival' },
  ],

  // MONOSPACE - Technical, Code-like, Modern
  monospace: [
    { name: 'Roboto Mono', weights: [400, 500, 700], description: 'Google monospace' },
    { name: 'Source Code Pro', weights: [400, 500, 600, 700], description: 'Adobe coding font' },
    { name: 'JetBrains Mono', weights: [400, 500, 600, 700], description: 'Developer favorite' },
    { name: 'Fira Code', weights: [400, 500, 600, 700], description: 'Ligatures for code' },
    { name: 'IBM Plex Mono', weights: [400, 500, 600, 700], description: 'IBM corporate mono' },
    { name: 'Space Mono', weights: [400, 700], description: 'Retro-futuristic' },
    { name: 'Inconsolata', weights: [400, 500, 600, 700], description: 'Clean coding font' },
    { name: 'Ubuntu Mono', weights: [400, 700], description: 'Ubuntu system font' },
    { name: 'Cousine', weights: [400, 700], description: 'Courier replacement' },
  ],

  // DISPLAY - Headlines, Impact, Creative
  display: [
    { name: 'Oswald', weights: [400, 500, 600, 700], description: 'Condensed gothic' },
    { name: 'Bebas Neue', weights: [400], description: 'All-caps display' },
    { name: 'Anton', weights: [400], description: 'Bold impact' },
    { name: 'Abril Fatface', weights: [400], description: 'Didone display' },
    { name: 'Righteous', weights: [400], description: 'Retro display' },
    { name: 'Archivo Black', weights: [400], description: 'Grotesque black' },
    { name: 'Fjalla One', weights: [400], description: 'Medium-contrast' },
    { name: 'Staatliches', weights: [400], description: 'Geometric display' },
    { name: 'Alfa Slab One', weights: [400], description: 'Heavy slab' },
  ],
};

// Generate Google Fonts URL for all fonts
const GOOGLE_FONTS_URL = 'https://fonts.googleapis.com/css2?' +
  'family=Inter:wght@400;500;600;700&' +
  'family=Roboto:wght@300;400;500;700&' +
  'family=Open+Sans:wght@400;600;700&' +
  'family=Lato:wght@400;700;900&' +
  'family=Source+Sans+Pro:wght@400;600;700&' +
  'family=Montserrat:wght@400;500;600;700&' +
  'family=Poppins:wght@400;500;600;700&' +
  'family=Nunito:wght@400;600;700&' +
  'family=Work+Sans:wght@400;500;600;700&' +
  'family=Raleway:wght@400;500;600;700&' +
  'family=Rubik:wght@400;500;600;700&' +
  'family=IBM+Plex+Sans:wght@400;500;600;700&' +
  'family=DM+Sans:wght@400;500;700&' +
  'family=Manrope:wght@400;500;600;700&' +
  'family=Plus+Jakarta+Sans:wght@400;500;600;700&' +
  'family=Merriweather:wght@400;700&' +
  'family=Playfair+Display:wght@400;500;600;700&' +
  'family=Lora:wght@400;500;600;700&' +
  'family=PT+Serif:wght@400;700&' +
  'family=Source+Serif+Pro:wght@400;600;700&' +
  'family=Libre+Baskerville:wght@400;700&' +
  'family=EB+Garamond:wght@400;500;600;700&' +
  'family=Spectral:wght@400;500;600;700&' +
  'family=IBM+Plex+Serif:wght@400;500;600;700&' +
  'family=Roboto+Mono:wght@400;500;700&' +
  'family=Source+Code+Pro:wght@400;500;600;700&' +
  'family=JetBrains+Mono:wght@400;500;600;700&' +
  'family=IBM+Plex+Mono:wght@400;500;600;700&' +
  'family=Oswald:wght@400;500;600;700&' +
  'family=Bebas+Neue&' +
  '&display=swap';

// Flat list for dropdown UI
const ALL_FONTS = [
  ...PROFESSIONAL_FONTS.sansSerif,
  ...PROFESSIONAL_FONTS.serif,
  ...PROFESSIONAL_FONTS.monospace,
  ...PROFESSIONAL_FONTS.display,
];
```

**Font Selection UI:**
```javascript
// Grouped dropdown for better UX
const fontSelectorHTML = `
<select id="font-family-select" class="font-selector">
  <optgroup label="Sans-Serif (Modern)">
    <option value="Inter">Inter</option>
    <option value="Roboto">Roboto</option>
    <option value="Open Sans">Open Sans</option>
    <!-- ... more -->
  </optgroup>
  <optgroup label="Serif (Traditional)">
    <option value="Merriweather">Merriweather</option>
    <option value="Playfair Display">Playfair Display</option>
    <option value="Lora">Lora</option>
    <!-- ... more -->
  </optgroup>
  <optgroup label="Monospace (Technical)">
    <option value="Roboto Mono">Roboto Mono</option>
    <option value="JetBrains Mono">JetBrains Mono</option>
    <!-- ... more -->
  </optgroup>
  <optgroup label="Display (Headlines)">
    <option value="Oswald">Oswald</option>
    <option value="Bebas Neue">Bebas Neue</option>
    <!-- ... more -->
  </optgroup>
</select>
`;
```

### 2.3 Text Colors: Professional CV Palette

**Curated color palette for professional CVs:**

```javascript
const CV_COLOR_PALETTE = {
  // PRIMARY TEXT COLORS - Main content
  primary: [
    { name: 'Charcoal', hex: '#1a1a1a', description: 'Standard body text' },
    { name: 'Soft Black', hex: '#2d2d2d', description: 'Softer alternative' },
    { name: 'Dark Gray', hex: '#333333', description: 'Classic professional' },
    { name: 'Graphite', hex: '#404040', description: 'Modern dark' },
  ],

  // SECONDARY TEXT COLORS - Subtle accents
  secondary: [
    { name: 'Medium Gray', hex: '#666666', description: 'Secondary info' },
    { name: 'Gray', hex: '#737373', description: 'Subdued text' },
    { name: 'Steel Gray', hex: '#71717a', description: 'Neutral accent' },
    { name: 'Slate', hex: '#64748b', description: 'Cool neutral' },
  ],

  // ACCENT COLORS - Headlines, links, emphasis
  accent: [
    // Blues (Corporate, Trust)
    { name: 'Navy', hex: '#1e3a5f', description: 'Corporate classic' },
    { name: 'Dark Blue', hex: '#1e40af', description: 'Trust & authority' },
    { name: 'Royal Blue', hex: '#2563eb', description: 'Links & highlights' },
    { name: 'Slate Blue', hex: '#475569', description: 'Subtle professional' },
    { name: 'Steel Blue', hex: '#334155', description: 'Modern corporate' },
    { name: 'Ocean', hex: '#0369a1', description: 'Tech industry' },

    // Greens (Growth, Success)
    { name: 'Forest', hex: '#166534', description: 'Nature & growth' },
    { name: 'Emerald', hex: '#059669', description: 'Fresh & modern' },
    { name: 'Teal', hex: '#0d9488', description: 'Tech & creative' },
    { name: 'Dark Teal', hex: '#115e59', description: 'Sophisticated' },

    // Reds & Burgundy (Energy, Leadership)
    { name: 'Burgundy', hex: '#7f1d1d', description: 'Executive, premium' },
    { name: 'Maroon', hex: '#881337', description: 'Bold leadership' },
    { name: 'Wine', hex: '#9f1239', description: 'Creative industries' },
    { name: 'Crimson', hex: '#b91c1c', description: 'Energy & passion' },

    // Purples (Creative, Innovation)
    { name: 'Deep Purple', hex: '#5b21b6', description: 'Creative roles' },
    { name: 'Violet', hex: '#6d28d9', description: 'Innovation' },
    { name: 'Plum', hex: '#7e22ce', description: 'Design & arts' },
    { name: 'Indigo', hex: '#4338ca', description: 'Tech & creative' },

    // Oranges & Browns (Warm, Approachable)
    { name: 'Chocolate', hex: '#78350f', description: 'Warm professional' },
    { name: 'Rust', hex: '#9a3412', description: 'Creative warmth' },
    { name: 'Amber', hex: '#b45309', description: 'Energy & optimism' },
    { name: 'Coffee', hex: '#44403c', description: 'Earthy sophistication' },
  ],

  // HIGHLIGHT COLORS - Background highlights (use sparingly)
  highlight: [
    { name: 'Light Yellow', hex: '#fef9c3', description: 'Attention' },
    { name: 'Light Blue', hex: '#dbeafe', description: 'Cool highlight' },
    { name: 'Light Green', hex: '#dcfce7', description: 'Success' },
    { name: 'Light Pink', hex: '#fce7f3', description: 'Warm emphasis' },
    { name: 'Light Gray', hex: '#f3f4f6', description: 'Subtle emphasis' },
  ],
};

// Color picker with preview
const colorPickerHTML = `
<div class="color-picker">
  <div class="color-palette-section">
    <label>Text Color</label>
    <div class="color-grid primary-colors">
      <button class="color-swatch" data-color="#1a1a1a" title="Charcoal" style="background:#1a1a1a"></button>
      <button class="color-swatch" data-color="#333333" title="Dark Gray" style="background:#333333"></button>
      <button class="color-swatch" data-color="#666666" title="Medium Gray" style="background:#666666"></button>
      <button class="color-swatch" data-color="#64748b" title="Slate" style="background:#64748b"></button>
    </div>
  </div>

  <div class="color-palette-section">
    <label>Accent Colors</label>
    <div class="color-grid accent-colors">
      <!-- Blues -->
      <button class="color-swatch" data-color="#1e3a5f" title="Navy" style="background:#1e3a5f"></button>
      <button class="color-swatch" data-color="#2563eb" title="Royal Blue" style="background:#2563eb"></button>
      <button class="color-swatch" data-color="#0369a1" title="Ocean" style="background:#0369a1"></button>
      <!-- Greens -->
      <button class="color-swatch" data-color="#166534" title="Forest" style="background:#166534"></button>
      <button class="color-swatch" data-color="#059669" title="Emerald" style="background:#059669"></button>
      <button class="color-swatch" data-color="#0d9488" title="Teal" style="background:#0d9488"></button>
      <!-- Reds/Burgundy -->
      <button class="color-swatch" data-color="#7f1d1d" title="Burgundy" style="background:#7f1d1d"></button>
      <button class="color-swatch" data-color="#881337" title="Maroon" style="background:#881337"></button>
      <button class="color-swatch" data-color="#b91c1c" title="Crimson" style="background:#b91c1c"></button>
      <!-- Purples -->
      <button class="color-swatch" data-color="#5b21b6" title="Deep Purple" style="background:#5b21b6"></button>
      <button class="color-swatch" data-color="#4338ca" title="Indigo" style="background:#4338ca"></button>
      <!-- Browns -->
      <button class="color-swatch" data-color="#78350f" title="Chocolate" style="background:#78350f"></button>
    </div>
  </div>

  <div class="color-palette-section">
    <label>Custom Color</label>
    <input type="color" id="custom-color" value="#1a1a1a">
    <input type="text" id="hex-input" placeholder="#1a1a1a" maxlength="7">
  </div>
</div>
`;

// TipTap extension for text color
const colorExtensionConfig = {
  types: ['textStyle'],
  HTMLAttributes: {
    style: ({ color }) => color ? { style: `color: ${color}` } : {},
  },
};
```

**Color Picker CSS:**
```css
.color-picker {
  padding: 12px;
  background: white;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  width: 240px;
}

.color-palette-section {
  margin-bottom: 12px;
}

.color-palette-section label {
  display: block;
  font-size: 11px;
  font-weight: 600;
  color: #666;
  margin-bottom: 6px;
  text-transform: uppercase;
}

.color-grid {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 4px;
}

.color-swatch {
  width: 28px;
  height: 28px;
  border-radius: 4px;
  border: 2px solid transparent;
  cursor: pointer;
  transition: transform 0.1s, border-color 0.1s;
}

.color-swatch:hover {
  transform: scale(1.1);
  border-color: #ddd;
}

.color-swatch.selected {
  border-color: #333;
  box-shadow: 0 0 0 2px white, 0 0 0 4px #333;
}

#custom-color {
  width: 40px;
  height: 28px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

#hex-input {
  width: 80px;
  padding: 4px 8px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-family: monospace;
  margin-left: 8px;
}
```

### 2.4 PDF Export: Playwright on VPS

**Why Playwright (detailed in Section 7):**
- ✅ Pixel-perfect rendering (real Chrome engine)
- ✅ Exact Google Fonts fidelity
- ✅ Professional page break handling
- ✅ ATS-compatible output (real PDF text, not images)
- ✅ Already have VPS infrastructure (runner service)

### 2.5 UI Framework: Vanilla JS + Tailwind CSS

Keep consistent with existing frontend. No React required.

---

## 3. Database Schema

### 3.1 MongoDB Schema Addition

```javascript
// Add to level-2 collection documents
{
  _id: ObjectId("691356b0d156e3f08a0bdb3d"),

  // ... existing fields (title, company, cover_letter, etc.) ...

  // NEW: Rich text CV editor state
  cv_editor_state: {
    // Schema version for future migrations
    version: 1,

    // TipTap document JSON
    content: {
      type: "doc",
      content: [
        {
          type: "heading",
          attrs: { level: 1 },
          content: [{ type: "text", text: "John Doe" }]
        },
        {
          type: "paragraph",
          content: [
            { type: "text", text: "Software Engineer", marks: [{ type: "bold" }] }
          ]
        },
        {
          type: "bulletList",
          content: [
            {
              type: "listItem",
              content: [
                {
                  type: "paragraph",
                  content: [{ type: "text", text: "Experience item" }]
                }
              ]
            }
          ]
        }
      ]
    },

    // Document-level styles
    documentStyles: {
      fontFamily: "Inter",
      fontSize: 11,
      lineHeight: 1.5,
      margins: {
        top: 0.75,    // inches
        right: 0.75,
        bottom: 0.75,
        left: 0.75
      },
      pageSize: "letter"  // letter, A4
    },

    // Metadata
    lastModified: ISODate("2025-11-26T19:30:00Z"),
    lastSavedAt: ISODate("2025-11-26T19:30:00Z"),

    // Optional: Version history (last 5 saves)
    history: [
      {
        savedAt: ISODate("2025-11-26T19:25:00Z"),
        content: { /* previous TipTap JSON */ }
      }
    ]
  },

  // LEGACY: Keep for backward compatibility
  cv_text: "# John Doe\n## Software Engineer\n..."
}
```

### 3.2 Migration Strategy

```python
# Migration script to add cv_editor_state from existing cv_text
def migrate_cv_to_editor_state(job):
    if job.get('cv_editor_state'):
        return  # Already migrated

    cv_text = job.get('cv_text', '')
    if cv_text:
        # Convert Markdown to TipTap JSON
        editor_state = markdown_to_tiptap(cv_text)

        db['level-2'].update_one(
            {'_id': job['_id']},
            {'$set': {'cv_editor_state': editor_state}}
        )
```

---

## 4. Component Architecture

### 4.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Job Detail Page                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                         Main Content Area                              │ │
│  │                                                                        │ │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────┐ │ │
│  │  │   Cover Letter   │  │   Pain Points    │  │     Contacts         │ │ │
│  │  └──────────────────┘  └──────────────────┘  └──────────────────────┘ │ │
│  │                                                                        │ │
│  │  ┌─────────────────────────────────────────────────────────────────┐  │ │
│  │  │   CV Preview Card                                               │  │ │
│  │  │   [Edit CV] Button ────────────────────────────────────────────►│  │ │
│  │  │                                                                 │  │ │
│  │  └─────────────────────────────────────────────────────────────────┘  │ │
│  │                                                                        │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                    CV Editor Side Panel (Right)                        │ │
│  │  ┌──────────────────────────────────────────────────────────────────┐  │ │
│  │  │  Header Bar                                                      │  │ │
│  │  │  [✕ Close] [↔ Expand/Collapse] [📄 Export PDF]    💾 Saved 3s   │  │ │
│  │  ├──────────────────────────────────────────────────────────────────┤  │ │
│  │  │  Floating Toolbar (position: sticky)                             │  │ │
│  │  │  ┌────────────────────────────────────────────────────────────┐  │  │ │
│  │  │  │ Font ▼ │ Size ▼ │ B │ I │ U │ • │ 1. │ ⇥ │ ≡ │ Ruler ▼    │  │  │ │
│  │  │  └────────────────────────────────────────────────────────────┘  │  │ │
│  │  ├──────────────────────────────────────────────────────────────────┤  │ │
│  │  │                                                                  │  │ │
│  │  │  Editor Canvas (A4/Letter preview)                               │  │ │
│  │  │  ┌──────────────────────────────────────────────────────────┐    │  │ │
│  │  │  │  ┌────────────────────────────────────────────────────┐  │    │  │ │
│  │  │  │  │ Ruler (margin indicators)                          │  │    │  │ │
│  │  │  │  ├────────────────────────────────────────────────────┤  │    │  │ │
│  │  │  │  │                                                    │  │    │  │ │
│  │  │  │  │  John Doe                                          │  │    │  │ │
│  │  │  │  │  Software Engineer | john@email.com                │  │    │  │ │
│  │  │  │  │                                                    │  │    │  │ │
│  │  │  │  │  EXPERIENCE                                        │  │    │  │ │
│  │  │  │  │  ─────────────────────────────────────────────     │  │    │  │ │
│  │  │  │  │  • Led team of 10 engineers...                     │  │    │  │ │
│  │  │  │  │  • Reduced incidents by 75%...                     │  │    │  │ │
│  │  │  │  │                                                    │  │    │  │ │
│  │  │  │  └────────────────────────────────────────────────────┘  │    │  │ │
│  │  │  └──────────────────────────────────────────────────────────┘    │  │ │
│  │  │                                                                  │  │ │
│  │  └──────────────────────────────────────────────────────────────────┘  │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 File Structure

```
frontend/
├── static/
│   ├── css/
│   │   └── cv-editor.css           # Editor-specific styles
│   └── js/
│       ├── cv-editor/
│       │   ├── index.js            # Main editor initialization
│       │   ├── tiptap-config.js    # TipTap setup & extensions
│       │   ├── toolbar.js          # Toolbar component
│       │   ├── side-panel.js       # Panel open/close/expand
│       │   ├── auto-save.js        # Debounced save logic
│       │   ├── pdf-export.js       # html2pdf integration
│       │   ├── fonts.js            # Google Fonts loader
│       │   └── ruler.js            # Ruler component
│       └── cv-editor.bundle.js     # Bundled for production
├── templates/
│   └── partials/
│       └── cv-editor-panel.html    # Editor side panel template
└── app.py                          # API endpoints for save/load
```

### 4.3 JavaScript Module Architecture

```javascript
// cv-editor/index.js
class CVEditor {
  constructor(jobId, initialState) {
    this.jobId = jobId;
    this.editor = null;
    this.saveStatus = 'saved';
    this.saveTimeout = null;
    this.AUTOSAVE_DELAY = 3000;

    this.initEditor(initialState);
    this.initToolbar();
    this.initAutoSave();
    this.initPDFExport();
  }

  initEditor(initialState) {
    this.editor = new Editor({
      element: document.querySelector('#cv-editor-content'),
      extensions: [
        StarterKit,
        Underline,
        TextAlign.configure({ types: ['heading', 'paragraph'] }),
        FontFamily,
        TextStyle,
        FontSize,
        Indent,
      ],
      content: initialState?.content || this.getDefaultContent(),
      onUpdate: () => this.onEditorUpdate(),
    });
  }

  onEditorUpdate() {
    this.saveStatus = 'unsaved';
    this.updateSaveIndicator();
    this.scheduleAutoSave();
  }

  scheduleAutoSave() {
    clearTimeout(this.saveTimeout);
    this.saveTimeout = setTimeout(() => this.save(), this.AUTOSAVE_DELAY);
  }

  async save() {
    this.saveStatus = 'saving';
    this.updateSaveIndicator();

    try {
      const state = {
        version: 1,
        content: this.editor.getJSON(),
        documentStyles: this.getDocumentStyles(),
        lastModified: new Date().toISOString(),
      };

      await fetch(`/api/jobs/${this.jobId}/cv-editor`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(state),
      });

      this.saveStatus = 'saved';
    } catch (err) {
      this.saveStatus = 'error';
      console.error('Save failed:', err);
    }

    this.updateSaveIndicator();
  }

  updateSaveIndicator() {
    const indicator = document.querySelector('#save-indicator');
    const icons = {
      unsaved: '○',
      saving: '◐',
      saved: '●',
      error: '⚠️',
    };
    const labels = {
      unsaved: 'Unsaved changes',
      saving: 'Saving...',
      saved: 'Saved',
      error: 'Save failed',
    };
    indicator.innerHTML = `${icons[this.saveStatus]} ${labels[this.saveStatus]}`;
  }

  async exportPDF() {
    const element = document.querySelector('#cv-editor-content');
    const opt = {
      margin: this.getDocumentStyles().margins,
      filename: `CV_${this.jobId}.pdf`,
      image: { type: 'jpeg', quality: 0.98 },
      html2canvas: { scale: 2, useCORS: true },
      jsPDF: { unit: 'in', format: 'letter', orientation: 'portrait' },
    };

    await html2pdf().set(opt).from(element).save();
  }
}
```

---

## 5. API Endpoints

### 5.1 Endpoint Specification

```python
# frontend/app.py

@app.route("/api/jobs/<job_id>/cv-editor", methods=["GET"])
@login_required
def get_cv_editor_state(job_id: str):
    """Get CV editor state for a job."""
    db = get_db()
    job = db["level-2"].find_one({"_id": ObjectId(job_id)})

    if not job:
        return jsonify({"error": "Job not found"}), 404

    editor_state = job.get("cv_editor_state")

    # If no editor state, migrate from cv_text
    if not editor_state and job.get("cv_text"):
        editor_state = migrate_markdown_to_tiptap(job["cv_text"])

    return jsonify({
        "success": True,
        "editor_state": editor_state or get_default_editor_state()
    })


@app.route("/api/jobs/<job_id>/cv-editor", methods=["PUT"])
@login_required
def save_cv_editor_state(job_id: str):
    """Save CV editor state to MongoDB."""
    db = get_db()

    try:
        object_id = ObjectId(job_id)
    except Exception:
        return jsonify({"error": "Invalid job ID"}), 400

    data = request.get_json()

    if not data or "content" not in data:
        return jsonify({"error": "Missing content"}), 400

    # Add server timestamp
    data["lastSavedAt"] = datetime.utcnow()

    result = db["level-2"].update_one(
        {"_id": object_id},
        {
            "$set": {
                "cv_editor_state": data,
                "updatedAt": datetime.utcnow()
            }
        }
    )

    if result.matched_count == 0:
        return jsonify({"error": "Job not found"}), 404

    return jsonify({"success": True, "savedAt": data["lastSavedAt"].isoformat()})


@app.route("/api/jobs/<job_id>/cv-editor/export-pdf", methods=["POST"])
@login_required
def export_cv_pdf(job_id: str):
    """Export CV as PDF (server-side for better fonts)."""
    # Optional: Server-side PDF generation for better quality
    # For now, use client-side html2pdf.js
    pass
```

---

## 6. Auto-Save System

### 6.1 Save Flow

```
User Types → Debounce Timer (3s) → Save to MongoDB → Update Indicator
     │                                    │
     │                                    ▼
     │                           On Success: "● Saved"
     │                           On Error: "⚠️ Save failed"
     │                                    │
     ▼                                    │
[Edit continues] ◄────────────────────────┘
```

### 6.2 Save Indicator States

| State | Icon | Color | Message |
|-------|------|-------|---------|
| Unsaved | ○ | Gray | "Unsaved changes" |
| Saving | ◐ | Blue (animated) | "Saving..." |
| Saved | ● | Green | "Saved" |
| Error | ⚠️ | Red | "Save failed - click to retry" |

### 6.3 Conflict Resolution

```javascript
// Handle concurrent edits (rare but possible)
async function saveWithConflictCheck(newState) {
  const currentJob = await fetch(`/api/jobs/${jobId}`).then(r => r.json());

  if (currentJob.cv_editor_state?.lastSavedAt > lastKnownSavedAt) {
    // Server has newer version - show conflict dialog
    showConflictDialog(currentJob.cv_editor_state, newState);
    return false;
  }

  return await save(newState);
}
```

---

## 7. PDF Export System (Playwright on VPS)

### 7.1 Architecture Overview

**Why Playwright over html2pdf.js:**
- ✅ Pixel-perfect rendering (real Chrome engine)
- ✅ Exact Google Fonts fidelity
- ✅ Professional page break handling
- ✅ ATS-compatible output (real PDF text, not images)
- ✅ Already have VPS infrastructure (runner service)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                         PDF EXPORT FLOW                                       │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  User clicks "Export PDF" (Vercel Frontend)                                   │
│         │                                                                     │
│         ▼                                                                     │
│  POST /api/cv/export-pdf                                                      │
│  Body: { jobId, tiptapJson, documentStyles }                                  │
│         │                                                                     │
│         ▼                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │  VPS Runner Service (runner_service/pdf_generator.py)                   │ │
│  │                                                                         │ │
│  │  1. Convert TipTap JSON → HTML with inline styles                       │ │
│  │  2. Inject Google Fonts CSS                                             │ │
│  │  3. Playwright launches headless Chrome                                 │ │
│  │  4. Render HTML → PDF with print media                                  │ │
│  │  5. Return PDF bytes                                                    │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│         │                                                                     │
│         ▼                                                                     │
│  Response: PDF blob (application/pdf)                                         │
│         │                                                                     │
│         ▼                                                                     │
│  Browser downloads: CV_{Company}_{Role}_{Date}.pdf                            │
│                                                                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 7.2 VPS Endpoint Implementation

```python
# runner_service/pdf_generator.py

from playwright.async_api import async_playwright
from typing import Dict, Any
import json

# Professional Google Fonts for CVs
GOOGLE_FONTS_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Roboto:wght@400;500;700&family=Open+Sans:wght@400;600;700&family=Lato:wght@400;700&family=Source+Sans+Pro:wght@400;600;700&family=Merriweather:wght@400;700&family=Playfair+Display:wght@400;700&display=swap');
"""

CV_BASE_STYLES = """
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: 'Inter', sans-serif;
  font-size: 11pt;
  line-height: 1.4;
  color: #1a1a1a;
}

h1 { font-size: 20pt; font-weight: 700; margin-bottom: 4pt; }
h2 { font-size: 13pt; font-weight: 600; text-transform: uppercase;
     border-bottom: 1.5pt solid #333; padding-bottom: 2pt; margin: 14pt 0 8pt 0; }
h3 { font-size: 11pt; font-weight: 600; margin: 8pt 0 4pt 0; }

ul, ol { margin-left: 18pt; margin-bottom: 6pt; }
li { margin-bottom: 3pt; }

p { margin-bottom: 6pt; }

.contact-line { font-size: 10pt; color: #444; margin-bottom: 10pt; }
"""


def tiptap_to_html(tiptap_json: Dict[str, Any], doc_styles: Dict[str, Any]) -> str:
    """Convert TipTap JSON document to styled HTML."""

    def render_marks(text: str, marks: list) -> str:
        """Apply marks (bold, italic, etc.) to text."""
        result = text
        style_attrs = []

        for mark in marks:
            mark_type = mark.get('type')
            attrs = mark.get('attrs', {})

            if mark_type == 'bold':
                result = f'<strong>{result}</strong>'
            elif mark_type == 'italic':
                result = f'<em>{result}</em>'
            elif mark_type == 'underline':
                result = f'<u>{result}</u>'
            elif mark_type == 'strike':
                result = f'<s>{result}</s>'
            elif mark_type == 'textStyle':
                if attrs.get('fontFamily'):
                    style_attrs.append(f"font-family: '{attrs['fontFamily']}', sans-serif")
                if attrs.get('fontSize'):
                    style_attrs.append(f"font-size: {attrs['fontSize']}")
                if attrs.get('color'):
                    style_attrs.append(f"color: {attrs['color']}")
            elif mark_type == 'highlight':
                if attrs.get('backgroundColor'):
                    style_attrs.append(f"background-color: {attrs['backgroundColor']}")

        if style_attrs:
            result = f'<span style="{"; ".join(style_attrs)}">{result}</span>'

        return result

    def render_node(node: Dict[str, Any]) -> str:
        """Recursively render a TipTap node to HTML."""
        node_type = node.get('type')
        attrs = node.get('attrs', {})
        content = node.get('content', [])

        # Text node
        if node_type == 'text':
            text = node.get('text', '')
            marks = node.get('marks', [])
            return render_marks(text, marks)

        # Block-level style attributes
        style_parts = []
        if attrs.get('textAlign'):
            style_parts.append(f"text-align: {attrs['textAlign']}")
        if attrs.get('indent'):
            style_parts.append(f"margin-left: {attrs['indent'] * 24}pt")
        style_attr = f' style="{"; ".join(style_parts)}"' if style_parts else ''

        # Render children
        inner = ''.join(render_node(child) for child in content)

        # Map node types to HTML
        if node_type == 'doc':
            return inner
        elif node_type == 'paragraph':
            return f'<p{style_attr}>{inner}</p>'
        elif node_type == 'heading':
            level = attrs.get('level', 1)
            return f'<h{level}{style_attr}>{inner}</h{level}>'
        elif node_type == 'bulletList':
            return f'<ul{style_attr}>{inner}</ul>'
        elif node_type == 'orderedList':
            return f'<ol{style_attr}>{inner}</ol>'
        elif node_type == 'listItem':
            return f'<li>{inner}</li>'
        elif node_type == 'hardBreak':
            return '<br>'
        elif node_type == 'horizontalRule':
            return '<hr>'
        else:
            return inner

    # Build complete HTML document
    margins = doc_styles.get('margins', {})
    page_size = doc_styles.get('pageSize', 'letter')

    # Page dimensions
    if page_size == 'letter':
        page_width, page_height = '8.5in', '11in'
    else:  # A4
        page_width, page_height = '210mm', '297mm'

    margin_css = f"""
        margin-top: {margins.get('top', 0.75)}in;
        margin-right: {margins.get('right', 0.75)}in;
        margin-bottom: {margins.get('bottom', 0.75)}in;
        margin-left: {margins.get('left', 0.75)}in;
    """

    body_content = render_node(tiptap_json)

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        {GOOGLE_FONTS_CSS}
        {CV_BASE_STYLES}

        @page {{
            size: {page_size};
            margin: 0;
        }}

        body {{
            width: {page_width};
            min-height: {page_height};
            {margin_css}
            font-family: '{doc_styles.get("fontFamily", "Inter")}', sans-serif;
            font-size: {doc_styles.get("fontSize", 11)}pt;
            line-height: {doc_styles.get("lineHeight", 1.4)};
        }}
    </style>
</head>
<body>
    {body_content}
</body>
</html>"""

    return html


async def generate_pdf(tiptap_json: Dict[str, Any], doc_styles: Dict[str, Any]) -> bytes:
    """Generate PDF from TipTap JSON using Playwright."""

    html_content = tiptap_to_html(tiptap_json, doc_styles)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # Set content and wait for fonts to load
        await page.set_content(html_content, wait_until='networkidle')

        # Generate PDF
        pdf_bytes = await page.pdf(
            format=doc_styles.get('pageSize', 'Letter'),
            print_background=True,
            margin={
                'top': f"{doc_styles.get('margins', {}).get('top', 0.75)}in",
                'right': f"{doc_styles.get('margins', {}).get('right', 0.75)}in",
                'bottom': f"{doc_styles.get('margins', {}).get('bottom', 0.75)}in",
                'left': f"{doc_styles.get('margins', {}).get('left', 0.75)}in",
            }
        )

        await browser.close()

    return pdf_bytes
```

### 7.3 Runner Service Endpoint

```python
# runner_service/app.py - Add this endpoint

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Dict, Any
from .pdf_generator import generate_pdf

class PDFExportRequest(BaseModel):
    job_id: str
    tiptap_json: Dict[str, Any]
    document_styles: Dict[str, Any]
    company: str
    role: str

@router.post("/cv/export-pdf")
async def export_cv_pdf(request: PDFExportRequest):
    """Generate professional PDF from TipTap editor state."""

    pdf_bytes = await generate_pdf(
        tiptap_json=request.tiptap_json,
        doc_styles=request.document_styles
    )

    # Generate filename
    safe_company = sanitize_filename(request.company)
    safe_role = sanitize_filename(request.role)
    date_str = datetime.now().strftime('%Y-%m-%d')
    filename = f"CV_{safe_company}_{safe_role}_{date_str}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


def sanitize_filename(name: str) -> str:
    """Sanitize string for use in filename."""
    import re
    safe = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    return safe[:50]  # Limit length
```

### 7.4 Frontend Export Function

```javascript
// frontend/static/js/cv-editor/pdf-export.js

async function exportCVToPDF() {
  const exportBtn = document.querySelector('#export-pdf-btn');
  const originalText = exportBtn.textContent;

  try {
    // Show loading state
    exportBtn.textContent = 'Generating PDF...';
    exportBtn.disabled = true;

    // Get current editor state
    const tiptapJson = editor.getJSON();
    const documentStyles = getDocumentStyles();

    // Call VPS endpoint
    const response = await fetch('/api/cv/export-pdf', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        job_id: jobId,
        tiptap_json: tiptapJson,
        document_styles: documentStyles,
        company: jobData.company,
        role: jobData.title,
      }),
    });

    if (!response.ok) {
      throw new Error(`Export failed: ${response.statusText}`);
    }

    // Download the PDF
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = response.headers.get('Content-Disposition')
      ?.match(/filename="(.+)"/)?.[1] || `CV_${jobData.company}.pdf`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);

    showToast('PDF exported successfully!', 'success');

  } catch (error) {
    console.error('PDF export failed:', error);
    showToast('PDF export failed. Please try again.', 'error');
  } finally {
    exportBtn.textContent = originalText;
    exportBtn.disabled = false;
  }
}
```

### 7.5 VPS Setup (One-time)

```bash
# Install Playwright and Chromium on VPS
pip install playwright
playwright install chromium
playwright install-deps  # Install system dependencies

# Verify installation
python -c "from playwright.sync_api import sync_playwright; print('Playwright OK')"
```

### 7.6 Professional CV Styling

The PDF generator applies these professional design principles:

| Element | Style |
|---------|-------|
| Name (H1) | 20pt, bold, primary color |
| Section Headers (H2) | 13pt, uppercase, bottom border |
| Body Text | 11pt, 1.4 line height |
| Bullet Points | Hanging indent, proper spacing |
| Margins | 0.75in all sides (adjustable) |
| Fonts | Google Fonts (Inter, Roboto, etc.) |

**ATS Compatibility:**
- Real selectable text (not images)
- Clean semantic HTML structure
- Standard fonts with fallbacks
- No complex layouts that confuse parsers

---

## 8. Memory Management & Performance

### 8.1 Performance Strategies

| Strategy | Implementation |
|----------|----------------|
| Debounced saves | 3-second delay prevents excessive writes |
| Virtual DOM | TipTap/ProseMirror uses efficient diffing |
| Lazy loading | Fonts loaded on-demand |
| Content chunking | Large documents split for efficient rendering |
| Cleanup on unmount | Proper event listener removal |

### 8.2 Memory Budget

```javascript
// Monitor memory usage
const MEMORY_WARNING_THRESHOLD = 100 * 1024 * 1024; // 100MB

function checkMemoryUsage() {
  if (performance.memory) {
    const used = performance.memory.usedJSHeapSize;
    if (used > MEMORY_WARNING_THRESHOLD) {
      console.warn(`High memory usage: ${Math.round(used / 1024 / 1024)}MB`);
      // Trigger garbage collection by nullifying references
      cleanupUnusedResources();
    }
  }
}

// Check every 30 seconds
setInterval(checkMemoryUsage, 30000);
```

### 8.3 Document Size Limits

```javascript
const MAX_CONTENT_SIZE = 500 * 1024; // 500KB max content

function validateContentSize(content) {
  const size = new Blob([JSON.stringify(content)]).size;
  if (size > MAX_CONTENT_SIZE) {
    showWarning('Document is very large. Consider reducing content for better performance.');
    return false;
  }
  return true;
}
```

---

## 9. Testing Strategy

### 9.1 Unit Tests

```python
# tests/frontend/test_cv_editor_api.py

class TestCVEditorAPI:
    """Tests for CV editor API endpoints."""

    def test_get_editor_state_not_found(self, client, mock_db):
        """GET editor state for non-existent job returns 404."""
        mock_db["level-2"].find_one.return_value = None
        response = client.get(f"/api/jobs/{ObjectId()}/cv-editor")
        assert response.status_code == 404

    def test_get_editor_state_success(self, client, mock_db):
        """GET editor state returns saved state."""
        mock_db["level-2"].find_one.return_value = {
            "_id": ObjectId(),
            "cv_editor_state": {"version": 1, "content": {"type": "doc"}}
        }
        response = client.get(f"/api/jobs/{ObjectId()}/cv-editor")
        assert response.status_code == 200
        assert response.json["editor_state"]["version"] == 1

    def test_save_editor_state_success(self, client, mock_db):
        """PUT editor state saves to MongoDB."""
        mock_db["level-2"].update_one.return_value = MagicMock(matched_count=1)
        response = client.put(
            f"/api/jobs/{ObjectId()}/cv-editor",
            json={"version": 1, "content": {"type": "doc", "content": []}}
        )
        assert response.status_code == 200
        assert response.json["success"] is True

    def test_save_editor_state_missing_content(self, client, mock_db):
        """PUT without content returns 400."""
        response = client.put(
            f"/api/jobs/{ObjectId()}/cv-editor",
            json={}
        )
        assert response.status_code == 400
```

### 9.2 Integration Tests

```javascript
// tests/frontend/cv-editor.test.js (Jest/Playwright)

describe('CV Editor', () => {
  test('opens side panel when Edit CV clicked', async () => {
    await page.click('[data-testid="edit-cv-btn"]');
    const panel = await page.waitForSelector('#cv-editor-panel');
    expect(await panel.isVisible()).toBe(true);
  });

  test('auto-saves after 3 seconds of inactivity', async () => {
    await page.click('[data-testid="edit-cv-btn"]');
    await page.type('#cv-editor-content', 'Test content');

    // Wait for auto-save
    await page.waitForSelector('#save-indicator:has-text("Saved")', { timeout: 5000 });

    // Verify MongoDB was updated
    const job = await db.collection('level-2').findOne({ _id: jobId });
    expect(job.cv_editor_state.content).toContain('Test content');
  });

  test('restores exact state on page reload', async () => {
    // Type and save
    await page.click('[data-testid="edit-cv-btn"]');
    await page.type('#cv-editor-content', 'Persistent content');
    await page.waitForSelector('#save-indicator:has-text("Saved")');

    // Reload page
    await page.reload();
    await page.click('[data-testid="edit-cv-btn"]');

    // Verify content restored
    const content = await page.textContent('#cv-editor-content');
    expect(content).toContain('Persistent content');
  });

  test('exports PDF to local machine', async () => {
    const downloadPromise = page.waitForEvent('download');
    await page.click('[data-testid="export-pdf-btn"]');
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/CV_.*\.pdf$/);
  });
});
```

### 9.3 E2E Tests

```python
# tests/e2e/test_cv_editor_e2e.py

@pytest.mark.e2e
class TestCVEditorE2E:
    """End-to-end tests for CV editor workflow."""

    def test_full_editing_workflow(self, browser, test_job):
        """Test complete CV editing and export workflow."""
        # Navigate to job detail
        browser.goto(f"/job/{test_job['_id']}")

        # Open editor
        browser.click("text=Edit CV")
        browser.wait_for_selector("#cv-editor-panel")

        # Edit content
        browser.fill("#cv-editor-content", "New CV Content")

        # Wait for auto-save
        browser.wait_for_selector("text=Saved", timeout=5000)

        # Export PDF
        with browser.expect_download() as download_info:
            browser.click("text=Export PDF")
        download = download_info.value
        assert download.path().endswith(".pdf")

        # Refresh and verify state restored
        browser.reload()
        browser.click("text=Edit CV")
        assert "New CV Content" in browser.text_content("#cv-editor-content")
```

---

## 10. Implementation Roadmap

### Phase 1: Foundation (4-6 hours)
- [ ] Set up TipTap with basic extensions
- [ ] Create side panel UI component
- [ ] Implement open/close/expand functionality
- [ ] Add basic toolbar (B/I/U)

### Phase 2: Rich Text Features (4-6 hours)
- [ ] Add Google Fonts integration
- [ ] Implement font family selector
- [ ] Add font size selector
- [ ] Implement bullet/numbered lists
- [ ] Add indentation controls

### Phase 3: Persistence (2-3 hours)
- [ ] Create API endpoints for save/load
- [ ] Implement auto-save with debounce
- [ ] Add save indicator UI
- [ ] Test state restoration

### Phase 4: PDF Export via Playwright (3-4 hours)
- [ ] Install Playwright + Chromium on VPS (`pip install playwright && playwright install chromium`)
- [ ] Create `runner_service/pdf_generator.py` with TipTap JSON → HTML → PDF conversion
- [ ] Add `/cv/export-pdf` endpoint to runner service
- [ ] Implement frontend export function with loading states
- [ ] Test PDF quality with various fonts and colors
- [ ] Add ATS compatibility verification

### Phase 5: Polish & Testing (3-4 hours)
- [ ] Add ruler component
- [ ] Implement keyboard shortcuts
- [ ] Write unit tests
- [ ] Write integration tests
- [ ] Performance optimization

**Total Estimated Time: 16-23 hours**

---

## 11. Fallback & Error Handling

### 11.1 Save Failures

```javascript
async function saveWithRetry(state, maxRetries = 3) {
  for (let i = 0; i < maxRetries; i++) {
    try {
      await save(state);
      return true;
    } catch (err) {
      if (i === maxRetries - 1) {
        // Store in localStorage as backup
        localStorage.setItem(`cv_backup_${jobId}`, JSON.stringify(state));
        showError('Save failed. Your changes are backed up locally.');
        return false;
      }
      await sleep(1000 * (i + 1)); // Exponential backoff
    }
  }
}
```

### 11.2 Local Backup Recovery

```javascript
function checkLocalBackup() {
  const backup = localStorage.getItem(`cv_backup_${jobId}`);
  if (backup) {
    const state = JSON.parse(backup);
    showDialog({
      title: 'Recover unsaved changes?',
      message: 'Found local backup from your last session.',
      actions: [
        { label: 'Recover', onClick: () => restoreBackup(state) },
        { label: 'Discard', onClick: () => localStorage.removeItem(`cv_backup_${jobId}`) },
      ]
    });
  }
}
```

---

## 12. Security Considerations

| Risk | Mitigation |
|------|------------|
| XSS in editor content | TipTap sanitizes HTML by default |
| Unauthorized access | `@login_required` decorator on all endpoints |
| Data injection | Validate TipTap JSON schema on server |
| Large payload DoS | 500KB content limit |

---

## 13. Browser Compatibility

| Browser | Minimum Version | Notes |
|---------|-----------------|-------|
| Chrome | 80+ | Full support |
| Firefox | 75+ | Full support |
| Safari | 13+ | Full support |
| Edge | 80+ | Full support |
| IE | Not supported | - |

---

## Appendix A: TipTap JSON Schema (Per-Element Styling)

**IMPORTANT**: TipTap uses a 3-tier styling system that supports unique styles on every character:

1. **Document-level** (`documentStyles`) - Page defaults (margins, page size)
2. **Block-level** (`attrs` on nodes) - Heading level, text alignment, indentation
3. **Inline-level** (`marks` on text nodes) - Per-character styling (font, color, bold, etc.)

```typescript
// Type definitions for editor state
interface EditorState {
  version: number;
  content: TipTapDocument;
  documentStyles: DocumentStyles;  // Page-level defaults only
  lastModified: string;
  lastSavedAt: string;
  history?: HistoryEntry[];
}

interface TipTapDocument {
  type: 'doc';
  content: TipTapNode[];
}

interface TipTapNode {
  type: string;  // 'heading', 'paragraph', 'bulletList', etc.
  attrs?: {
    level?: number;      // For headings (1-6)
    textAlign?: string;  // 'left' | 'center' | 'right' | 'justify'
    indent?: number;     // Indentation level
  };
  content?: TipTapNode[];
  marks?: TipTapMark[];  // Only on text nodes - PER-CHARACTER STYLING
  text?: string;         // Only on text nodes
}

// MARKS: Per-character styling - each text span can have unique styles
interface TipTapMark {
  type: 'bold' | 'italic' | 'underline' | 'strike' | 'textStyle' | 'highlight';
  attrs?: {
    // textStyle mark attributes (per-character)
    fontFamily?: string;   // e.g., "Inter", "Playfair Display"
    fontSize?: string;     // e.g., "12px", "18pt"
    color?: string;        // e.g., "#1a1a1a", "rgb(26, 54, 93)"
    // highlight mark attributes
    backgroundColor?: string;
  };
}

interface DocumentStyles {
  fontFamily: string;   // Default font (fallback when no textStyle mark)
  fontSize: number;     // Default size in pt
  lineHeight: number;   // e.g., 1.5
  margins: {
    top: number;        // inches
    right: number;
    bottom: number;
    left: number;
  };
  pageSize: 'letter' | 'A4';
}
```

### Example: Mixed Styles in Single Paragraph

```javascript
// "Senior Software Engineer | john@email.com"
// where "Senior" is regular Inter 12px,
// "Software Engineer" is bold+italic Playfair 14px navy,
// and "john@email.com" is blue underlined

{
  type: "paragraph",
  attrs: { textAlign: "center" },
  content: [
    {
      type: "text",
      text: "Senior ",
      marks: [
        { type: "textStyle", attrs: { fontFamily: "Inter", fontSize: "12px" } }
      ]
    },
    {
      type: "text",
      text: "Software Engineer",
      marks: [
        { type: "textStyle", attrs: {
          fontFamily: "Playfair Display",
          fontSize: "14px",
          color: "#1e3a5f"
        }},
        { type: "bold" },
        { type: "italic" }
      ]
    },
    {
      type: "text",
      text: " | ",
      marks: []  // Uses document defaults
    },
    {
      type: "text",
      text: "john@email.com",
      marks: [
        { type: "textStyle", attrs: { color: "#2563eb" } },
        { type: "underline" }
      ]
    }
  ]
}
```

**Key Points:**
- Each `text` node can have its own unique combination of marks
- Marks are additive - stack bold + italic + color + font on same text
- When restored from MongoDB, exact per-character styling is preserved
- TipTap handles mark merging/splitting automatically during editing
- Document styles only apply where no explicit textStyle mark exists

---

## Appendix B: Quick Reference Card

**Keyboard Shortcuts:**
- `Ctrl+B` - Bold
- `Ctrl+I` - Italic
- `Ctrl+U` - Underline
- `Ctrl+S` - Manual save
- `Tab` - Indent
- `Shift+Tab` - Outdent
- `Esc` - Close panel

**API Endpoints:**
- `GET /api/jobs/{id}/cv-editor` - Load state
- `PUT /api/jobs/{id}/cv-editor` - Save state
- `POST /api/jobs/{id}/cv-editor/export-pdf` - Server-side PDF (optional)

**MongoDB Field:**
- `cv_editor_state` - Rich text editor JSON state
