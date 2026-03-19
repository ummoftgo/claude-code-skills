---
name: use-context7
description: "Query up-to-date library and framework documentation before writing code. Use when working with PHP, Svelte, HTMX, jQuery, or any third-party library/framework to ensure correct API usage, avoid deprecated patterns, and get version-specific guidance. Trigger before writing non-trivial code that depends on external library APIs."
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
# 라이브러리 ID 조회
npx ctx7 library htmx

# 문서 조회 (라이브러리 ID + 쿼리)
npx ctx7 docs /bigskysoftware/htmx "hx-swap hx-trigger"
npx ctx7 docs /sveltejs/svelte "$state $derived runes"
npx ctx7 docs /php/php-src "PDO prepared statements"
```

`ctx7`도 없으면 WebSearch/WebFetch로 공식 문서를 직접 조회한다.
