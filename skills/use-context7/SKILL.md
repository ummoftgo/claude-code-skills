---
name: use-context7
description: "Fetch current library documentation before writing non-trivial code that depends on an external library, framework, SDK, or API — PHP extensions, Svelte runes/lifecycle, HTMX attributes, jQuery plugins, third-party APIs. Library APIs drift between versions, so do not rely on training knowledge for signatures or configuration. Uses the Context7 CLI (`npx ctx7@latest`); the Context7 MCP tools are an alternative when they are connected. When another skill says 'invoke use-context7 if installed', this is the skill to call."
---

# Use Context7

Query the library's current documentation before writing code against it.

## When

Query when the code depends on a library API you have not verified in this session, when a version-specific pattern is involved (Svelte 5 runes vs. stores, PHP 8.x extension changes), or when the library may have had breaking changes.

Skip when the operation is plain language syntax, when that library's docs are already in this session's context, or when the API is trivially version-independent.

## Workflow (CLI)

Two commands; both take the question as a required second argument. Write the query as the concrete question, not a keyword — `"how do I bind PDO prepared statement parameters safely?"` retrieves better docs than `"PDO"`.

```bash
# 1. Resolve the library ID — use the official spelling ("Next.js", "Three.js", "HTMX")
npx ctx7@latest library "HTMX" "which hx-swap values re-run scripts in the swapped fragment?"

# 2. Query docs with the returned /org/project ID (or /org/project/version)
npx ctx7@latest docs /bigskysoftware/htmx "which hx-swap values re-run scripts in the swapped fragment?"
```

Pick the result by exact name match, description relevance, snippet count, source reputation, and benchmark score; prefer the official library over wrappers or tutorials. Run at most three commands per question. Do not put secrets or proprietary code in a query.

In PowerShell, single-quote queries containing `$state` or other dollar-prefixed identifiers so they are not expanded.

When a task touches two libraries (PHP PDO and Svelte, for example), query each separately; a combined query returns weaker results.

Apply the returned signatures, version-specific patterns, and deprecation notices as written.

## Failure handling

- Quota error: tell the user and suggest `npx ctx7@latest login` or setting `CONTEXT7_API_KEY`. Do not silently fall back to training knowledge.
- DNS or network failure inside a sandbox (Codex: `ENOTFOUND`, `fetch failed`): rerun the command outside the sandbox instead of retrying inside it.
- If the Context7 MCP tools (`resolve-library-id`, `query-docs`) are connected, they take the same two arguments and may replace the CLI. If neither is available, use web search or fetch against the official documentation site.
