# CSS / SCSS Quality Reference

CLI tools and manual patterns for CSS/SCSS quality review.

## Table of Contents
1. [CLI Tool Setup](#1-cli-tool-setup)
2. [Running the Tools](#2-running-the-tools)
3. [Comment Quality](#3-comment-quality)
4. [Style Conventions & Naming](#4-style-conventions--naming)
5. [Duplication & Variables](#5-duplication--variables)
6. [Performance & Specificity](#6-performance--specificity)
   - [Specificity Escalation](#61-specificity-escalation)
   - [SCSS Nesting Depth](#62-scss-nesting-depth)
   - [Dead CSS](#63-dead-css)

---

## 1. CLI Tool Setup

```bash
# Stylelint — primary CSS/SCSS linter
if [ ! -f node_modules/.bin/stylelint ]; then
  npm install --save-dev stylelint

  # Choose config based on project:
  # Plain CSS
  npm install --save-dev stylelint-config-standard
  # SCSS
  npm install --save-dev stylelint-config-standard-scss
fi
```

**Config file detection** (`stylelint.config.*`, `.stylelintrc.*`, `stylelint` key in `package.json`):
- If a config already exists → run as-is
- If no config → create a minimal one before running:

```js
// .stylelintrc.json (plain CSS)
{ "extends": ["stylelint-config-standard"] }

// .stylelintrc.json (SCSS)
{ "extends": ["stylelint-config-standard-scss"] }
```

---

## 2. Running the Tools

### Stylelint
```bash
# Compact output for review
npx stylelint "**/*.css" "**/*.scss" --formatter=compact

# Verbose (shows rule names — useful for diagnosing findings)
npx stylelint "**/*.css" "**/*.scss"

# Auto-fix safe issues (formatting, property order)
npx stylelint "**/*.css" "**/*.scss" --fix

# Specific directory
npx stylelint "src/**/*.scss" --formatter=compact
```

---

## 3. Comment Quality

### Flag
```scss
// BAD — restates code
color: red; // set color to red

// BAD — commented-out dead CSS
// .old-header { padding: 20px; }

// BAD — stale TODO with no owner/ticket
// TODO: fix this someday
```

### Keep
```scss
// GOOD — explains non-obvious workaround
// z-index 100: must sit above the sticky nav (z-index: 90)
.modal { z-index: 100; }

// GOOD — documents browser-specific fix
// Safari < 15 ignores gap in flex; using margin fallback
.flex-row > * { margin-right: 8px; }
```

---

## 4. Style Conventions & Naming

Infer project conventions from existing code majority. Flag deviations only.

### Naming consistency
```scss
// BAD — mixed conventions in same project
.user-card { }        // kebab-case
.userCard { }         // camelCase
.UserCard { }         // PascalCase
```

### BEM (if project uses it)
```scss
// BAD — arbitrary modifier without BEM structure
.card-active { }

// GOOD — BEM modifier
.card--active { }
.card__title { }
```

### Property ordering
Stylelint's `order` plugin (if configured) handles this. Manually flag:
```scss
// BAD — positioning mixed with typography
.box {
  font-size: 14px;
  position: absolute;  // ← out of expected group order
  color: red;
  top: 0;
}
```

Common order convention (detect from project majority):
`positioning → box model → typography → visual → misc`

---

## 5. Duplication & Variables

### Magic numbers — repeated values without custom properties
```scss
// BAD — same color hex in 8 different files
.header { background: #2d3748; }
.sidebar { background: #2d3748; }

// GOOD — CSS custom property
:root { --color-surface-dark: #2d3748; }
.header  { background: var(--color-surface-dark); }
.sidebar { background: var(--color-surface-dark); }
```

### SCSS variable vs custom property
```scss
// BAD — SCSS variable not reused (define once, use once)
$header-bg: #2d3748;
.header { background: $header-bg; }

// GOOD if used in 3+ places; otherwise inline is clearer
```

### Grep patterns for duplication
```bash
# Repeated hex colors
grep -rh "#[0-9a-fA-F]\{3,6\}" --include="*.css" --include="*.scss" \
  | grep -oE "#[0-9a-fA-F]{3,6}" | sort | uniq -d

# Repeated pixel values (magic numbers)
grep -rh "[0-9]\+px" --include="*.css" --include="*.scss" \
  | grep -oE "[0-9]+px" | sort | uniq -c | sort -rn | head -20

# Same selector defined in multiple files
grep -rh "^\." --include="*.css" --include="*.scss" \
  | sort | uniq -d | head -20
```

---

## 6. Performance & Specificity

### 6.1 Specificity Escalation

Core principle: **keep specificity flat** — overly specific selectors are hard to override and create maintenance debt.

```scss
// BAD — deep descendant selector (fragile, high specificity)
div#main-content > section.article-list ul.items li.item a.link { color: blue; }

// GOOD — single class (low specificity, resilient)
.article-link { color: blue; }
```

```scss
// BAD — !important as a shortcut
.button { color: red !important; }

// GOOD — fix the specificity root cause instead
// Only acceptable: utility override classes (.u-hidden, .sr-only) with documented reason
```

### Grep patterns
```bash
# All !important usages
grep -rn "!important" --include="*.css" --include="*.scss"

# Deep selectors (4+ levels)
grep -rn "^\s*[a-zA-Z#.][^{]*[a-zA-Z#.][^{]*[a-zA-Z#.][^{]*[a-zA-Z#.][^{]*{" \
  --include="*.css" --include="*.scss"
```

### 6.2 SCSS Nesting Depth

Keep nesting ≤ 3 levels. Deeper nesting generates high-specificity selectors and is hard to read.

```scss
// BAD — 4 levels deep
.card {
  .header {
    .title {
      span { font-weight: bold; }  // ← generates .card .header .title span
    }
  }
}

// GOOD — flatten with BEM or a direct class
.card { }
.card__header { }
.card__title { }
.card__title-text { font-weight: bold; }
```

```scss
// BAD — & chaining creates unreadable generated selectors
.nav {
  &--active {
    &:hover {
      & > .icon { opacity: 1; }   // ← .nav--active:hover > .icon
    }
  }
}
```

### Grep
```bash
# Files with deep nesting (heuristic: 4+ consecutive indented blocks)
grep -rn "^\s\{12,\}" --include="*.scss"   # 12+ spaces = ~3 levels at 4sp indent
```

### 6.3 Dead CSS

Tools cannot reliably detect dead CSS without running the full app. Check manually:

- Selectors referencing classes that no longer exist in HTML/templates
- `@keyframes` defined but never referenced by `animation`
- SCSS `@mixin` defined but never `@include`d
- CSS custom properties defined in `:root` but never used

```bash
# Unused @keyframes
grep -rn "@keyframes" --include="*.css" --include="*.scss" \
  | awk '{print $2}' | while read name; do
    grep -rq "animation.*$name\|animation-name.*$name" --include="*.css" --include="*.scss" --include="*.php" --include="*.js" \
      || echo "Possibly unused keyframe: $name"
  done

# Unused SCSS mixins
grep -rn "@mixin" --include="*.scss" | awk '{print $2}' | tr -d '(' \
  | while read name; do
    grep -rq "@include $name" --include="*.scss" \
      || echo "Possibly unused mixin: $name"
  done
```
