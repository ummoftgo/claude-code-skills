# Implementation handoff details

Supporting detail for `SKILL.md` → *Mode 2: Implement*. Reviews never need this
file.

## Splitting the work

Only split when the parts are genuinely independent. One `codex -a never exec -s
workspace-write` call per part, each with its own explicit file scope.

| Split | When | Calls |
|---|---|---|
| Backend + Frontend | API contract already agreed, both sides independent | 2 |
| Layout + Logic | Single page, markup and JS separable | 2 |
| Single | Small task, or the parts share files | 1 |

Every call must state:

- the exact files it may create or edit;
- the hard constraint "do not touch files outside this scope";
- the conventions it must follow (naming, response shape, style).

## After the calls return

1. **Overlap check** — confirm no two calls edited the same file.
2. **Naming consistency** — API endpoint paths, DB column names, and shared
   identifiers must match across layers.
3. **Happy path** — run the app and exercise the feature end to end.
4. **Cleanup** — delete any context file you created for the task.

## Context file template

Use this only when the context is too large for the prompt or must be reused across
several calls. Name it `YYYYMMDD-HHMMSS-{type}-{slug}.md` so concurrent tasks never
collide, keep it in `.agent-works/` (recommended in `.gitignore`), reference its path
in the prompt, and delete it when the task finishes.

```markdown
# Task: implement — [feature name]
**Date**: [YYYY-MM-DD HH:MM]

## Project Overview
[Tech stack: backend language/framework, frontend approach, DB, auth]

## Current State
[Work done so far; recently changed files]

## Task Description
[What to implement, precisely]

## Relevant Files
[Explicit list of in-scope paths]

## Constraints
[Conventions, files that must not be touched, naming rules]

## Interface Contract
[API shape shared across layers, e.g. {"success": bool, "data": ..., "error": "..."}]
```
