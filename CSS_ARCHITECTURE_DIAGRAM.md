# CSS Architecture Diagram & Technical Reference
**For:** GraphAML Sidebar Styling System (as of April 10, 2026, v11.14)

---

## CSS Cascade Flow (Priority Order)

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. BOOTSTRAP 5.x (Baseline)                                     │
│    - Grid, typography, utilities                                │
│    - Lowest specificity                                         │
└────────────────────────┬────────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. BASE.CSS (Core AML Sidebar — v5.14 Premium)                  │
│    - Sidebar layout (position: fixed, height 100vh)             │
│    - Header: logo, brand, bell, day/night toggle               │
│    - Nav groups with headers (uppercase labels)                │
│    - Nav items (7px padding, rounded, hover translate)         │
│    - Group headers: border-top separator, color: #64748B        │
│    - ✨ Nav item active: gradient bg + left border + shadow    │
│    - ✨ Step badges + per-group #grp-* colors:                  │
│      #grp-orientation (slate #64748b)                           │
│      #grp-executive-summary (amber #f59e0b)                     │
│      #grp-risk-intelligence (rose #f43f5e)                      │
│      #grp-network-analysis (sky #38bdf8)                        │
│      #grp-compliance-actions (indigo #818cf8)                   │
│      #grp-analyst-tools (emerald #34d399)                       │
│      #grp-system (slate #94a3b8)                                │
│    - Search box (focus state, rounded)                          │
│    - Mode toggle button base (basic styling — was invisible!)   │
│    - Footer: user block, theme dropdown, PII toggle, logout     │
│    - Scrollbar: 2px width, transparent track, primary-dim thumb │
└────────────────────────┬────────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. ULTRAPREMIUM.CSS (Aurora Shimmer + Modern Effects)           │
│    - Sidebar::before: aurora shimmer animation (200px height)   │
│    - Logo: gradient ring + hover glow + rotate(-2deg)          │
│    - Brand: gradient text (blue→purple)                         │
│    - Nav items: 11px border-radius (smooth, modern)            │
│    - Nav item active: gradient bg + gradient left border glow   │
│    - Group headers: uppercase, grey color, spacing tweaks       │
│    - Scrollbar: gradient thumb (purple→cyan)                    │
│    - Avatar: gradient ring + glow                               │
│    - Status strip: gradient animated dot                        │
│    - Topbar: glassmorphism, blur(32px), backdrop-filter        │
└────────────────────────┬────────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. PREMIUM.CSS / ELITE.CSS / *_DS.CSS (Theme Variants)          │
│    - Theme-specific color overrides                             │
│    - Component-level tweaks for specific themes                 │
│    - Lower specificity — doesn't override base                  │
└────────────────────────┬────────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. DOJ-INSPIRED-ENHANCEMENTS.CSS (ADDITIVE LAYER — v11.14)       │
│    ⚠️  MUST BE ADDITIVE ONLY — NEVER RE-DEFINE EXISTING RULES   │
│                                                                  │
│    ✨ MODE TOGGLE (NEW — NOT IN BASE.CSS):                       │
│       - .nav-mode-toggle: purple gradient + glow                │
│       - .nav-mode-toggle--analyst: emerald gradient + glow      │
│       - Hover: stronger glow + translateY(-1px)                │
│       - Letter-spacing: 0.04em (uppercase feel)                │
│                                                                  │
│    ✨ STEP BADGES (NEW — NOT IN BASE.CSS):                       │
│       - .sg-step-badge: 18x18px circle, centered               │
│       - Font: 0.6rem, 800 weight (bold number)                 │
│       - Box-shadow: white ring + depth shadow                   │
│       - Used by sidebar.py: <html.Span step, class="sg-step">  │
│                                                                  │
│    ✨ SCROLLBAR GRADIENT (ENHANCEMENT):                          │
│       - .sidebar-nav::-webkit-scrollbar-thumb                   │
│       - Gradient: purple → sky blue                             │
│                                                                  │
│    ✨ LIVE BADGE ANIMATION (ENHANCEMENT):                        │
│       - @keyframes badge-pop: scale(0.4) → scale(1.18) → 1     │
│       - Cubic-bezier spring feel                                │
│       - 0.3s duration                                           │
│                                                                  │
│    ❌ REMOVED (v11.13 bugs):                                     │
│       - margin-left: 20px on .sidebar-group-items              │
│       - border-radius: 0 6px 6px 0 on .sidebar-nav-item        │
│       - Duplicate .sb-sections::before (base.css has it)       │
│       - Duplicate #grp-* colors (base.css has them)            │
│       - Duplicate .sidebar-nav-item.active (base.css has it)   │
└────────────────────────┬────────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 6. INLINE STYLES (Component-Level)                              │
│    - Added via sidebar.py: style={"color": color, ...}         │
│    - Highest specificity                                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Sidebar.py → CSS Mapping

### HTML Structure Generated by `sidebar.py`

```html
<div id="sidebar" class="sidebar">
  
  <!-- Header -->
  <div class="sidebar-header">
    <div class="sidebar-logo">📊</div>
    <div class="ax-brand-block">
      <span class="ax-brand-name">GraphAML</span>
      <span class="ax-brand-sub">Apex — Graph & Network Intelligence</span>
      <span class="ax-brand-badge">v11.4.0 · APEX GRAPH DS</span>
    </div>
    <div class="sidebar-bell-wrap"></div>
    <button class="sidebar-icon-btn" id="daynight-toggle-btn"></button>
    <button class="sidebar-icon-btn" id="sidebar-collapse-btn"></button>
  </div>
  
  <!-- MODE TOGGLE (Executive/Analyst) -->
  <div class="nav-mode-toggle-wrapper px-2 mb-2">
    <button id="nav-mode-toggle-btn" class="nav-mode-toggle" n_clicks=0>
      🛠️ Analyst Mode  <!-- or 👁️ Executive View if in analyst mode -->
    </button>
  </div>
  
  <!-- SEARCH BOX -->
  <div class="sidebar-search-wrap">
    <input class="sidebar-search" placeholder="🔍 Search navigation…" />
  </div>
  
  <!-- NAVIGATION (Main Content) -->
  <nav class="sidebar-nav flex-fill">
    <div class="sb-sections">
      <!-- Generated by build_sidebar() for each group in _NAV_EXECUTIVE -->
      
      <!-- GROUP 1: Orientation -->
      <div id="grp-orientation" class="sidebar-group">
        <div class="sidebar-group-header sidebar-group-header--toggle">
          <svg class="iconify" data-icon="mdi:compass" width="14"></svg>
          <span class="flex-fill">ORIENTATION</span>
          <span class="sg-chevron ms-1">▾</span>
        </div>
        <div class="sidebar-group-items">
          <a href="/about" class="sidebar-nav-item">
            <svg class="iconify" data-icon="mdi:lightbulb-outline" width="16"></svg>
            About GraphAML
          </a>
          <a href="/user-guide" class="sidebar-nav-item">
            <svg class="iconify" data-icon="mdi:book-open-variant" width="16"></svg>
            User Guide
          </a>
          <a href="/process-flow" class="sidebar-nav-item">
            <svg class="iconify" data-icon="mdi:diagram-2" width="16"></svg>
            Process Flow
          </a>
        </div>
      </div>
      
      <!-- GROUP 2: Executive Summary (with STEP BADGE) -->
      <div id="grp-executive-summary" class="sidebar-group">
        <div class="sidebar-group-header sidebar-group-header--toggle">
          <svg class="iconify" data-icon="mdi:speedometer" width="14"></svg>
          <span class="sg-step-badge" style="background:#f59e0b">1</span>
          <span class="flex-fill">EXECUTIVE SUMMARY</span>
          <span class="sg-chevron ms-1">▾</span>
        </div>
        <div class="sidebar-group-items">
          <a href="/executive-summary" class="sidebar-nav-item">
            <svg class="iconify"></svg>
            Intelligence Summary
          </a>
          <!-- more items... -->
        </div>
      </div>
      
      <!-- Similar for other groups... -->
      <!-- GROUP 3: Risk Intelligence (step badge: 2, rose) -->
      <!-- GROUP 4: Network Analysis (step badge: 3, sky) -->
      <!-- GROUP 5: Compliance & Actions (step badge: 4, indigo) -->
      <!-- GROUP 6: Analyst Tools (step badge: 5, emerald) — shown only in analyst mode -->
      <!-- GROUP 7: System (no step badge, grey) -->
      
    </div> <!-- /.sb-sections -->
  </nav>
  
  <!-- FOOTER -->
  <div class="sidebar-footer">
    <div class="sidebar-status-strip">
      <span class="status-dot offline"></span>
      <span>No pipeline data</span>
    </div>
    
    <div class="mb-3">
      <div class="sidebar-group-header mb-1">THEME</div>
      <select id="theme-dropdown" class="graphaml-dropdown"><option>...</option></select>
    </div>
    
    <div class="pii-toggle-wrap d-flex align-items-center gap-2">
      <input type="checkbox" id="pii-mask-toggle" />
      <label>🔒 Mask PII</label>
    </div>
    
    <div class="user-block d-flex align-items-center gap-2">
      <div class="avatar">AJ</div>  <!-- initials -->
      <div class="flex-fill">
        <div class="user-name">Alice Johnson</div>
        <div class="user-role">analyst</div>
      </div>
      <button class="logout-btn">🚪</button>
    </div>
  </div>
  
</div>
```

### CSS Selector Mapping

| HTML Class/ID | CSS Rule Location | Purpose |
|---|---|---|
| `.sidebar` | base.css:576 | Main container (position: fixed, 100vh height) |
| `.sidebar-header` | base.css:599 | Top section with logo + brand |
| `.sidebar-logo` | base.css:611 | Logo icon (40x40px) |
| `.ax-brand-name` | base.css | "GraphAML" text |
| `.ax-brand-sub` | base.css | Tagline text |
| `.ax-brand-badge` | base.css | Version badge |
| `.nav-mode-toggle-wrapper` | base.css:1735 | Wraps mode toggle button |
| `.nav-mode-toggle` | **base.css:1736** | Executive mode button (base) |
| | **doj-enhanced.css** | ✨ Enhanced with gradient+glow |
| `.nav-mode-toggle--analyst` | **base.css:1747** | Analyst mode button (base) |
| | **doj-enhanced.css** | ✨ Enhanced with emerald gradient |
| `.sidebar-search-wrap` | base.css:1906 | Search container |
| `.sidebar-search` | base.css:1910 | Input field |
| `.sidebar-nav` | base.css:643 | Main nav scrollable area |
| `.sb-sections` | base.css:1923* | Wrapper for all groups (*added in v11.8) |
| `.sb-sections::before` | base.css:1923 | Gradient connector line (spine) |
| `.sidebar-group` | base.css:651 | Single group container |
| `#grp-orientation` | base.css:2010 | Group ID (dynamically generated) |
| `#grp-executive-summary` | base.css:2011 | Group ID (step badge: 1, amber) |
| `#grp-risk-intelligence` | base.css:2012 | Group ID (step badge: 2, rose) |
| `#grp-network-analysis` | base.css:2013 | Group ID (step badge: 3, sky) |
| `#grp-compliance-actions` | base.css:2014 | Group ID (step badge: 4, indigo) |
| `#grp-analyst-tools` | base.css:2015 | Group ID (step badge: 5, emerald) |
| `#grp-system` | base.css:2016 | Group ID (no step badge) |
| `.sidebar-group-header` | base.css:653 | Group title row |
| `.sidebar-group-header--toggle` | base.css:739 | Clickable group header |
| `.sg-step-badge` | **doj-enhanced.css** ✨ | Circular numbered pill (1,2,3...) |
| `.sg-chevron` | base.css:745 | Expand/collapse chevron |
| `.sidebar-group-items` | base.css:750 | Items container (with left border) |
| `.sidebar-nav-item` | base.css:663 | Individual nav link |
| `.sidebar-nav-item:hover` | base.css:672 | Hover state (translate + bg) |
| `.sidebar-nav-item.active` | base.css:676 | Active/current page (glow + border) |
| `.sidebar-footer` | base.css:705 | Bottom section |
| `.sidebar-status-strip` | base.css | Pipeline status indicator |
| `.status-dot` | base.css | Animated dot |
| `.user-block` | base.css | User info + logout |
| `.avatar` | base.css | User initials circle |
| `.user-name` | base.css | User full name |
| `.user-role` | base.css | User role (analyst, manager, etc.) |

---

## Group ID Generation Logic (sidebar.py)

```python
# From sidebar.py, _build_group() function

group_id = "grp-" + (
    group["group"]
    .lower()
    .replace(" & ", "-")    # "Compliance & Actions" → "compliance-actions"
    .replace("&", "")       # Remove any remaining ampersands
    .replace(" ", "-")      # Replace spaces with hyphens
)

# Examples:
"Orientation" → "grp-orientation"
"Executive Summary" → "grp-executive-summary"
"Risk Intelligence" → "grp-risk-intelligence"
"Network Analysis" → "grp-network-analysis"
"Compliance & Actions" → "grp-compliance-actions"
"Analyst Tools" → "grp-analyst-tools"
"System" → "grp-system"
```

This allows CSS to target groups without modifying Python:
```css
#grp-executive-summary .sidebar-group-header {
  border-left-color: #f59e0b;  /* amber */
}
#grp-executive-summary .sidebar-nav-item.active {
  color: #fde68a;  /* light amber text */
}
```

---

## Color Palette (Group Accents)

| Group | ID | Step | CSS Color | Hex | Use |
|---|---|---|---|---|---|
| Orientation | `grp-orientation` | — | slate | #64748b | Left border, not a step |
| Executive Summary | `grp-executive-summary` | 1 | amber | #f59e0b | Step badge, left border, active text |
| Risk Intelligence | `grp-risk-intelligence` | 2 | rose | #f43f5e | Step badge, left border, active text |
| Network Analysis | `grp-network-analysis` | 3 | sky | #38bdf8 | Step badge, left border, active text |
| Compliance & Actions | `grp-compliance-actions` | 4 | indigo | #818cf8 | Step badge, left border, active text |
| Analyst Tools | `grp-analyst-tools` | 5 | emerald | #34d399 | Step badge, left border, active text |
| System | `grp-system` | — | slate | #94a3b8 | Left border, not a step |

---

## CSS Specificity Hierarchy

```
LOWEST  ┌─────────────────────────┐
        │ .sidebar-nav-item       │  (element class)
        │ Specificity: 0,1,1      │
        ├─────────────────────────┤
        │ .sidebar-nav-item:hover │  (pseudo-class)
        │ Specificity: 0,2,1      │
        ├─────────────────────────┤
        │ #grp-executive-summary  │
        │ .sidebar-nav-item       │  (ID + class)
        │ Specificity: 1,1,1      │
        ├─────────────────────────┤
        │ .sidebar-nav-item       │  (class only)
        │ style={"color": "..."}  │  (inline style)
        │ Specificity: 1,0,0      │
HIGHEST └─────────────────────────┘
```

**Rule:** DOJ CSS should NOT use `!important` (it breaks the cascade). Let specificity do the work:
- Use ID selectors (`#grp-*`) for group-specific rules
- Use inline styles (sidebar.py) for component-level overrides
- Use class selectors for global rules

---

## Files Architecture

```
GraphAML_v11.14/
│
├── config.yaml                    ← version, port, settings
├── app.py                         ← main Dash app
│
├── assets/
│   ├── bootstrap.min.css          ← Baseline (lowest specificity)
│   ├── base.css                   ← Core sidebar premium (v5.14 section at line 1900)
│   ├── ultrapremium.css           ← Aurora + effects (overlays base)
│   ├── premium.css, elite.css     ← Theme variants
│   ├── doj-inspired-enhancements.css  ← DOJ layer (additive, line 115)
│   ├── *_ds.css                   ← Other design system files
│   └── fonts/                     ← Font files
│
└── dash_app/
    ├── layouts/
    │   └── sidebar.py             ← build_sidebar() generates HTML
    ├── pages/
    │   ├── about.py
    │   ├── dashboard.py
    │   └── ...
    ├── callbacks/
    │   └── ...
    └── ...
```

---

## Key CSS Rules Reference

### Sidebar Position (Must be `fixed`, not `sticky`)
```css
.sidebar {
  position: fixed;  /* ✓ Correct */
  left: 0;
  top: 0;
  bottom: 0;
  width: var(--sidebar-width);
  z-index: 1000;
}

/* ❌ WRONG — Don't do this */
.sidebar { position: sticky; }  /* Breaks sidebar scroll behavior */
```

### Group Header Colors
```css
/* Base rule in base.css */
.sidebar-group-header {
  border-left: 3px solid transparent;
  color: #64748b;
}

/* Per-group override in base.css */
#grp-executive-summary .sidebar-group-header {
  border-left-color: #f59e0b;
}

/* ✓ Let cascade work — don't re-define in doj CSS */
```

### Mode Toggle Evolution
```css
/* v10.11 base.css (simple but functional) */
.nav-mode-toggle {
  background: rgba(255,255,255,0.04);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  padding: 0.38rem 0.75rem;
}

/* v11.14 doj-inspired-enhancements.css (enhanced) */
.nav-mode-toggle {
  background: linear-gradient(135deg, rgba(124,58,237,0.12) 0%, ...);
  border-color: rgba(124,58,237,0.32);
  color: #a78bfa;
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.07), 0 1px 4px rgba(0,0,0,0.25);
  letter-spacing: 0.04em;
  /* ✓ Creates visual emphasis — button is now discoverable */
}
```

---

## How to Debug Sidebar Issues

### Step 1: Identify the CSS Rule
1. Open Browser DevTools (F12)
2. Inspect element (Ctrl+Shift+C)
3. Click on the element you want to debug
4. Look at "Styles" panel → see all rules applied + which file

### Step 2: Check CSS Cascade
- Rules can be overridden by:
  - More specific selectors
  - Rules later in the file
  - Rules in files loaded after (later in cascade)
  - `!important` rules

### Step 3: Verify File Order
- Check `<head>` in browser DevTools
- See order: bootstrap → base → ultrapremium → doj-enhanced
- If rule is not applying, check if it's being overridden by a later file

### Step 4: Clear Cache
```bash
# Remove all cache directories
Remove-Item -Recurse -Force cache, diskcache, __pycache__ -ErrorAction SilentlyContinue

# Restart app
python app.py

# Hard refresh in browser
Ctrl+Shift+Delete (or Cmd+Shift+Delete on Mac)
```

---

**Last Updated:** April 10, 2026 (v11.14)  
**Diagram Status:** ✅ Complete and current
