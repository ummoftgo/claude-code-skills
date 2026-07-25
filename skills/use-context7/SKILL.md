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
- A `find-docs` skill is also installed in this environment and has already retrieved Context7 documentation for the same library in this session — reuse those results instead of running a duplicate Context7 lookup

## Workflow

### Step 1: Resolve Library ID

Call `mcp__context7__resolve-library-id` with the library name and the question you need answered.

```
mcp__context7__resolve-library-id({
  libraryName: "Svelte",
  query: "how do $state and $derived runes replace stores in Svelte 5?"
})
```

Use the library's official spelling and punctuation — `"Next.js"`, `"Three.js"`, `"HTMX"` — not `nextjs` or `threejs`.

Pick the most relevant result (IDs look like `/org/project`). Prefer the official library over wrappers or tutorials, and weigh exact name match, description relevance, snippet count, source reputation, and benchmark score.

### Step 2: Query Relevant Docs

Call `mcp__context7__query-docs` with the resolved ID and the same concrete question.

```
mcp__context7__query-docs({
  libraryId: "/sveltejs/svelte",
  query: "how do $state and $derived runes replace stores in Svelte 5?"
})
```

Write `query` as a specific question, not a single keyword — `"how do I bind PDO prepared statement parameters safely?"` retrieves better docs than `"PDO"`. Other examples: `"which hx-swap values re-run scripts in the swapped fragment?"`, `"how do I delegate events with jQuery .on() for dynamically added rows?"`.

For version-specific docs, use a versioned ID from the Step 1 output (e.g. `/vercel/next.js/v14.3.0`).

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

If Context7 MCP tools are not available, use the `ctx7` CLI. Both subcommands take the query as a required second argument.

The `npx` commands work in both POSIX shells and PowerShell. In PowerShell, keep queries containing `$state` or other dollar-prefixed identifiers in single quotes so they are not expanded as variables.

```bash
# Resolve library ID: ctx7 library <name> <query>
npx ctx7@latest library "HTMX" "hx-swap and hx-trigger behavior"

# Query docs: ctx7 docs <libraryId> <query>
npx ctx7@latest docs /bigskysoftware/htmx "which hx-swap values re-run scripts in the swapped fragment?"
npx ctx7@latest docs /sveltejs/svelte 'how do $state and $derived runes replace stores in Svelte 5?'
```

The same rules apply as for the MCP tools: use the library's official spelling (`"Next.js"`, `"Three.js"`), and phrase the query as the concrete question rather than a single keyword.

If a command fails with a quota error, tell the user and suggest `npx ctx7@latest login` or setting the `CONTEXT7_API_KEY` environment variable for higher limits. Do not silently fall back to training knowledge.

If `ctx7` is also unavailable, fall back to WebSearch/WebFetch against the official documentation site.
