# JavaScript Frontend Quality Reference

Browser-surface review: DOM, jQuery, Svelte, and HTMX. Tool invocation and the
environment-neutral patterns (comments, style, duplication) live in `js-toolchain.md` —
read that first, then this file for anything that only matters in a browser.

> **The read-only rule in `SKILL.md` overrides every instruction in this file.** Under a
> read-only request, no command here may install a tool, create a config file, write a
> report file, or auto-fix code — regardless of what an individual section says. Each
> write-causing command below carries its own read-only contract line; when one is
> skipped, record it in the report with its reason.

## Table of Contents
1. [Performance & Evaluation Order](#1-performance--evaluation-order)
   - [Vanilla JS](#11-vanilla-js)
   - [jQuery](#12-jquery)
   - [Svelte](#13-svelte)
   - [HTMX](#14-htmx)
2. [Style & Duplication on the Browser Surface](#2-style--duplication-on-the-browser-surface)
3. [Svelte Lifecycle & Store Subscription](#3-svelte-lifecycle--store-subscription)

---

## 1. Performance & Evaluation Order

ESLint/Biome catch some issues; the patterns below require manual review.

### 1.1 Vanilla JS

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

### 1.2 jQuery

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

### 1.3 Svelte

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

### 1.4 HTMX

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

## 2. Style & Duplication on the Browser Surface

Environment-neutral style and duplication rules are in `js-toolchain.md` §4–5. These only apply
where a DOM exists.

**Svelte component structure**:
- Consistent section order: `<script>`, markup, `<style>`
- Svelte 5: use `$props()` / `$state()` / `$derived()` — don't mix with Svelte 4 `export let` / stores

```js
// BAD — same DOM selector queried multiple times
document.querySelector('#submit-btn').disabled = true;
document.querySelector('#submit-btn').textContent = 'Saving...';
// → const btn = document.querySelector('#submit-btn');

// BAD — near-identical jQuery event handlers
$('#save-btn').on('click', () => $.post('/api/save', formData(), handleResponse));
$('#publish-btn').on('click', () => $.post('/api/publish', formData(), handleResponse));
// → $('[data-action]').on('click', function() { $.post('/api/' + $(this).data('action'), ...) })
```

```bash
# Repeated selectors — the same string queried in more than one place
rg -n "querySelector\(" --glob "*.{js,svelte}" . | awk -F'"' '{print $2}' | sort | uniq -d
```

## 3. Svelte Lifecycle & Store Subscription

> **Review principle**: Always read the full component before flagging a lifecycle or subscription issue.
> Isolated pattern matching produces false positives — the same code is correct or incorrect
> depending on how the store/subscription is actually used in context.

### 3.1 Auto-subscription vs. manual subscription

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

### 3.2 Svelte 5 — `$effect` cleanup

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

### 3.3 Module-scope stores (`<script context="module">`)

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

### 3.4 Audit grep

```bash
# Manual subscribe calls — check each for onDestroy cleanup
grep -rn "\.subscribe(" --include="*.svelte" -n

# $effect without return (check if external resource is registered inside)
grep -rn "\$effect(" --include="*.svelte" -A 10 | grep -v "return () =>"

# onDestroy usage — confirm it's paired with a subscribe or addEventListener
grep -rn "onDestroy" --include="*.svelte" -n
```
