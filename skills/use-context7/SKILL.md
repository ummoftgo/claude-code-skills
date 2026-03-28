---
name: use-context7
description: "INVOKE THIS SKILL BY NAME ('use-context7') before writing any non-trivial code that depends on an external library or framework — PHP extensions, Svelte runes/lifecycle, HTMX attributes, jQuery plugins, or any third-party API. Do not rely on training knowledge for library APIs; documentation drifts and versions change. Querying first prevents deprecated patterns, wrong signatures, and version-specific mistakes. When another skill instructs 'invoke use-context7 if installed', this is the skill to call."
---

# Use Context7

Before writing code that relies on an external library or framework, query its latest documentation via Context7 MCP tools. This prevents using deprecated APIs, wrong function signatures, or outdated patterns.

## When to Use

**Always query** when:
- Writing code for a library/framework you haven't used recently
- Implementing a feature where you're unsure of the correct API
- Working with PHP extensions, Svelte runes/lifecycle, HTMX attributes, jQuery plugins
- The library may have had breaking changes in recent versions

**Skip** when:
- The operation is pure language syntax (vanilla PHP loops, basic JS array methods)
- You already queried this library in the current session and the docs are still in context
- The API is trivially obvious and version-independent (e.g., `console.log`, `echo`)

## Workflow

### Step 1: Resolve Library ID

Call `mcp__context7__resolve-library-id` with the library name.

```
mcp__context7__resolve-library-id({ libraryName: "svelte" })
mcp__context7__resolve-library-id({ libraryName: "htmx" })
mcp__context7__resolve-library-id({ libraryName: "laravel" })
```

Pick the most relevant result. Prefer the official library over wrappers or tutorials.

### Step 2: Query Relevant Docs

Call `mcp__context7__query-docs` with the resolved ID and a focused topic string.

```
mcp__context7__query-docs({
  context7CompatibleLibraryID: "/sveltejs/svelte",
  topic: "runes $state $derived reactivity",
  tokens: 5000
})
```

**Topic guidance by stack:**

| Stack | Example topic strings |
|-------|----------------------|
| PHP (PDO) | `"PDO prepared statements bindParam execute"` |
| PHP (sessions) | `"session_start session_regenerate_id cookie options"` |
| Svelte 5 | `"$state $derived $effect runes component lifecycle"` |
| HTMX | `"hx-post hx-swap hx-trigger hx-target response swapping"` |
| jQuery | `"ajax .on() .html() event delegation deferred"` |

Adjust `tokens` based on complexity: 3000 for simple lookups, 8000 for architecture-level questions.

### Step 3: Write Code Based on Docs

Read the returned documentation carefully. Apply:
- The exact function signatures shown
- Version-specific patterns (e.g., Svelte 5 runes vs Svelte 4 stores)
- Any deprecation notices

## Multiple Libraries in One Task

When a task touches both PHP backend and a frontend framework, query both:

1. Resolve and query the backend library (e.g., PHP PDO)
2. Resolve and query the frontend library (e.g., Svelte stores)
3. Proceed with implementation informed by both

Do not batch into a single query — separate queries yield more focused results.

## Fallback: No MCP Available

If Context7 MCP tools are not available, use the `ctx7` CLI:

```bash
# Resolve library ID
npx ctx7 library htmx

# Query docs (library ID + topic)
npx ctx7 docs /bigskysoftware/htmx "hx-swap hx-trigger"
npx ctx7 docs /sveltejs/svelte "$state $derived runes"
npx ctx7 docs /php/php-src "PDO prepared statements"
```

If `ctx7` is also unavailable, fall back to WebSearch/WebFetch against the official documentation site.
