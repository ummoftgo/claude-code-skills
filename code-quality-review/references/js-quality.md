# JavaScript / jQuery / Svelte / HTMX Quality Reference

CLI tools and manual patterns for frontend quality review.

## Table of Contents
1. [CLI Tool Setup](#1-cli-tool-setup)
2. [Running the Tools](#2-running-the-tools)
3. [Comment Quality](#3-comment-quality)
4. [Style Conventions](#4-style-conventions)
5. [Duplication](#5-duplication)
6. [Performance & Evaluation Order](#6-performance--evaluation-order)
   - [Vanilla JS](#61-vanilla-js)
   - [jQuery](#62-jquery)
   - [Svelte](#63-svelte)
   - [HTMX](#64-htmx)

---

## 1. CLI Tool Setup

Tools are project-local (npm). Install only what is missing.

```bash
# ESLint — use if eslint.config.js / .eslintrc.* exists in project
if [ ! -f node_modules/.bin/eslint ]; then
  npm install --save-dev eslint
fi

# Biome — use if biome.json exists (replaces ESLint + Prettier)
if [ ! -f node_modules/.bin/biome ]; then
  npm install --save-dev --save-exact @biomejs/biome
  # First time: npx @biomejs/biome init
fi

# Oxlint — use for large codebases or alongside ESLint for speed
if [ ! -f node_modules/.bin/oxlint ]; then
  npm install --save-dev oxlint
fi

# svelte-check — install if .svelte files exist
if ls src/**/*.svelte &>/dev/null 2>&1 || ls *.svelte &>/dev/null 2>&1; then
  if [ ! -f node_modules/.bin/svelte-check ]; then
    npm install --save-dev svelte-check
  fi
fi

# knip — unused exports, files, dependencies
if [ ! -f node_modules/.bin/knip ]; then
  npm install --save-dev knip
fi
```

**Tool selection priority**:
1. If `biome.json` exists → use Biome (`check` covers lint + format)
2. Else if `eslint.config.*` or `.eslintrc.*` exists → use ESLint
3. Else → install ESLint (most compatible default)

---

## 2. Running the Tools

### ESLint
```bash
# Report only (no auto-fix)
npx eslint . --format=compact

# With specific directories
npx eslint src/ --format=compact --max-warnings=0

# JSON output for scripting
npx eslint . --format=json -o eslint-report.json

# Auto-fix safe issues
npx eslint . --fix
```

### Biome
```bash
# Lint + format check combined
npx @biomejs/biome check .

# CI mode (stricter — fails on warnings too)
npx @biomejs/biome ci .

# Auto-fix
npx @biomejs/biome check --write .
```

### Oxlint
```bash
# Fast lint pass (good for large codebases)
npx oxlint .

# With TypeScript support
npx oxlint --tsconfig tsconfig.json .

# Auto-fix
npx oxlint --fix .
```

### svelte-check
```bash
# Machine-readable output
npx svelte-check --output machine

# Verbose (includes warnings)
npx svelte-check --output machine-verbose

# Check specific directory
npx svelte-check --workspace src/
```

### knip — unused code & dependencies
```bash
# Full report: unused files, exports, dependencies
npx knip

# Fix automatically where possible
npx knip --fix

# Specific category
npx knip --include files          # only unused files
npx knip --include dependencies   # only unused npm packages
npx knip --include exports        # only unused exports
```

---

## 3. Comment Quality

### Flag
```js
// BAD — restates code
const total = items.length; // get the total

// BAD — stale JSDoc (param type wrong)
/**
 * @param {String} id   ← should be number
 */
function getUser(id) { ... }

// BAD — commented-out dead code
// const oldApi = fetch('/api/v1/users');
const data = await fetch('/api/v2/users');
```

### Keep
```js
// GOOD — explains non-obvious behaviour
// Debounce 300ms: avoids search API call on every keystroke
const debouncedSearch = debounce(search, 300);

// GOOD — intentional workaround with reason
// Safari < 16 lacks :has() support; toggling class manually instead
```

---

## 4. Style Conventions

Detect project majority first (ESLint/Biome handle most of this). Flag manually:

```js
// BAD — var in an ES6+ project
var count = 0;

// BAD — .then() mixed into async/await function
async function loadUser() {
    const res = await fetch('/api/user');
    return res.json().then(u => u);   // ← inconsistent
}

// BAD — mixed quote style in same file
const a = 'hello';
const b = "world";
```

**Svelte-specific**:
- Consistent section order: `<script>`, markup, `<style>`
- Svelte 5: use `$props()` / `$state()` / `$derived()` — don't mix with Svelte 4 `export let` / stores

---

## 5. Duplication

knip covers unused exports. Also flag manually:

```js
// BAD — same fetch + error handling in 5 files
const res = await fetch('/api/users');
if (!res.ok) throw new Error('Failed');
const data = await res.json();
// → extract to api(url, options) helper

// BAD — same DOM selector queried multiple times
document.querySelector('#submit-btn').disabled = true;
document.querySelector('#submit-btn').textContent = 'Saving...';
// → const btn = document.querySelector('#submit-btn');

// BAD — near-identical jQuery event handlers
$('#save-btn').on('click', () => $.post('/api/save', formData(), handleResponse));
$('#publish-btn').on('click', () => $.post('/api/publish', formData(), handleResponse));
// → $('[data-action]').on('click', function() { $.post('/api/' + $(this).data('action'), ...) })
```

### Grep patterns
```bash
grep -rn "await fetch(" --include="*.js" --include="*.svelte" | sort
grep -rn "querySelector(" --include="*.js" | awk -F'"' '{print $2}' | sort | uniq -d
```

---

## 6. Performance & Evaluation Order

ESLint/Biome catch some issues; the patterns below require manual review.

### 6.1 Vanilla JS

#### Guard before expensive operation
```js
// BAD — DOM query runs even when input is invalid
function updateUser(id, data) {
    const el = document.getElementById(`user-${id}`);  // always runs
    if (!id || !data) return;
    el.textContent = data.name;
}

// GOOD
function updateUser(id, data) {
    if (!id || !data) return;                           // cheap guard first
    const el = document.getElementById(`user-${id}`);
    el.textContent = data.name;
}
```

#### Cache DOM queries outside loops
```js
// BAD — forces reflow each iteration
items.forEach(item => {
    document.querySelector('.list').appendChild(createRow(item));
});

// GOOD — single query + DocumentFragment batch
const list = document.querySelector('.list');
const frag = document.createDocumentFragment();
items.forEach(item => frag.appendChild(createRow(item)));
list.appendChild(frag);
```

#### includes before regex
```js
// BAD — regex engine spin-up for simple substring
if (/error/.test(message)) { }

// GOOD
if (message.includes('error')) { }
```

#### Optional chaining over typeof guard
```js
// BAD
if (typeof config !== 'undefined' && config.debug === true) { }

// GOOD
if (config?.debug) { }
```

### 6.2 jQuery

#### Cache selectors
```js
// BAD — re-queries DOM on every call
$('#form input').val('');
$('#form .error').hide();

// GOOD
const $form = $('#form');
$form.find('input').val('');
$form.find('.error').hide();
```

#### Batch class changes
```js
// BAD — three separate style recalculations
$el.addClass('active');
$el.addClass('visible');
$el.addClass('ready');

// GOOD
$el.addClass('active visible ready');
```

#### Event delegation over per-element binding
```js
// BAD — N handlers, breaks on dynamic content
$('.delete-btn').on('click', handler);

// GOOD — one handler on stable parent
$('#list').on('click', '.delete-btn', handler);
```

#### Grep
```bash
grep -rn "\.addClass\b" --include="*.js" -A1 | grep -B1 "\.addClass\b"  # chained addClass
grep -rn "\$('.*')\." --include="*.js" | awk -F"'" '{print $2}' | sort | uniq -d  # repeated selectors
```

### 6.3 Svelte

#### Move heavy computation out of template
```svelte
<!-- BAD — filter + sort on every render -->
{#each items.filter(i => i.active).sort((a,b) => b.date - a.date) as item}

<!-- GOOD — reactive declaration runs only when items changes -->
<script>
  $: activeItems = items.filter(i => i.active).sort((a,b) => b.date - a.date);
  // Svelte 5: const activeItems = $derived(items.filter(...).sort(...));
</script>
{#each activeItems as item}
```

#### Derived store over full store subscription
```js
// BAD — fires on any store change
$: userName = $userStore.profile.name;

// GOOD — only fires when name changes
import { derived } from 'svelte/store';
const userName = derived(userStore, $u => $u.profile.name);
```

#### Keyed each for dynamic lists
```svelte
<!-- BAD — DOM reuse causes state bugs -->
{#each items as item}

<!-- GOOD -->
{#each items as item (item.id)}
```

#### Audit grep
```bash
grep -rn "{@html" --include="*.svelte"                         # XSS + unnecessary HTML rendering
grep -rn "\.filter\|\.sort\|\.map" --include="*.svelte"        # heavy ops in template
```

### 6.4 HTMX

#### Prefer events over polling
```html
<!-- BAD — polls every 2 seconds regardless of change -->
<div hx-get="/api/status" hx-trigger="every 2s">

<!-- GOOD — triggered by server-sent event or user action -->
<div hx-get="/api/status" hx-trigger="statusChanged from:body">
```

#### Target specific element, not body
```html
<!-- BAD — full page swap for small update -->
<button hx-get="/api/count" hx-target="body">

<!-- GOOD -->
<button hx-get="/api/count" hx-target="#item-count" hx-swap="innerHTML">
```

#### Prevent duplicate requests
```html
<!-- GOOD — disables button while request is in flight -->
<button hx-post="/api/save"
        hx-disabled-elt="this"
        hx-indicator="#spinner">Save</button>
```

#### Audit grep
```bash
grep -rn "every [0-9]" --include="*.html" --include="*.php"        # polling intervals
grep -rn 'hx-target.*["\x27]body["\x27]' --include="*.html" --include="*.php"  # full-page swap
```
