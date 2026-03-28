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
7. [Svelte Lifecycle & Store Subscription](#7-svelte-lifecycle--store-subscription)

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

---

## 7. Svelte Lifecycle & Store Subscription

> **Review principle**: Always read the full component before flagging a lifecycle or subscription issue.
> Isolated pattern matching produces false positives — the same code is correct or incorrect
> depending on how the store/subscription is actually used in context.

### 7.1 Auto-subscription vs. manual subscription

Svelte's `$store` reactive syntax **automatically unsubscribes** when the component is destroyed.
Never flag this pattern as a leak — it is safe by design:

```svelte
<script>
  import { userStore } from './stores.js';
  // SAFE — Svelte handles unsubscription on component destroy
</script>
<p>{$userStore.name}</p>
```

```svelte
<script>
  import { writable } from 'svelte/store';
  // SAFE — local store used with $ syntax; auto-cleaned up with the component
  const count = writable(0);
</script>
<p>{$count}</p>
```

Manual `.subscribe()` calls, however, **do require explicit cleanup**:

```svelte
<script>
  import { onDestroy } from 'svelte';
  import { userStore } from './stores.js';

  // BAD — subscription never released; runs after component is destroyed
  userStore.subscribe(user => { ... });

  // GOOD — explicit cleanup
  const unsub = userStore.subscribe(user => { ... });
  onDestroy(unsub);

  // ALSO GOOD — return unsub from onDestroy directly
  onDestroy(userStore.subscribe(user => { ... }));
</script>
```

**Before flagging a subscription as a leak, confirm**:
1. Is it using `.subscribe()` directly (not `$store` syntax)?
2. Is there no `onDestroy` that returns or calls the unsubscribe function anywhere in the component?
3. Is the store not a derived or readable that auto-completes?

Only flag if all three are true.

### 7.2 Svelte 5 — `$effect` cleanup

In Svelte 5, `$effect` runs setup code and optionally returns a cleanup function.
A missing cleanup is only a problem when the effect sets up an external resource (event listener, timer, WebSocket).

```svelte
<script>
  // BAD — event listener leaks after component unmounts
  $effect(() => {
    window.addEventListener('resize', handleResize);
    // missing: return () => window.removeEventListener('resize', handleResize);
  });

  // GOOD
  $effect(() => {
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  });

  // FINE — no external resource, no cleanup needed
  $effect(() => {
    console.log('count changed:', count);
  });
</script>
```

**Only flag `$effect` without a return when it registers an external listener or resource.**
Pure side effects (logging, updating local state, calling an API) do not need cleanup.

### 7.3 Module-scope stores (`<script context="module">`)

Stores declared in `<script context="module">` are shared across **all instances** of the component.
They are intentionally persistent — do not flag them as missing cleanup.
Do flag if mutable module-scope state causes cross-instance contamination:

```svelte
<script context="module">
  // POTENTIALLY PROBLEMATIC — if multiple instances share and mutate this
  export const sharedSelection = writable(null);
  // Flag only if the intent is per-instance state (should be in <script> instead)
</script>
```

### 7.4 Audit grep

```bash
# Manual subscribe calls — check each for onDestroy cleanup
grep -rn "\.subscribe(" --include="*.svelte" -n

# $effect without return (check if external resource is registered inside)
grep -rn "\$effect(" --include="*.svelte" -A 10 | grep -v "return () =>"

# onDestroy usage — confirm it's paired with a subscribe or addEventListener
grep -rn "onDestroy" --include="*.svelte" -n
```
