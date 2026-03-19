---
name: web-parallel-dispatch
description: "Dispatch multiple sub-agents in parallel to accelerate web development tasks. Use when: (1) API contract is finalized and PHP backend + frontend can be built simultaneously, (2) multiple independent pages or components need implementation, (3) a feature can be split into DB schema + API + frontend work, (4) UI layout and JS logic are independent. Saves significant time vs. sequential implementation."
---

# Web Parallel Dispatch

Accelerate web development by dispatching independent work to parallel sub-agents. Each agent works on a separate, well-defined scope and returns a summary of what it built.

## When to Use

**Good signals for parallelization:**
- API contract is written and agreed upon → backend and frontend can proceed independently
- Multiple pages/features have no shared state with each other
- DB schema is stable → schema migration, API layer, and frontend can split
- UI structure (HTML/CSS) and JS behavior are clearly separable

**Do not parallelize when:**
- Work is sequential (e.g., must deploy DB migration before writing API)
- Agents would edit the same files
- One agent's output is the other's input (pipeline, not parallel)
- Scope is unclear — clarify first, then dispatch

## Patterns

Four patterns cover most PHP + JS/Svelte/HTMX scenarios. See `references/dispatch-patterns.md` for full agent prompt templates.

| Pattern | When to use | Agents |
|---------|-------------|--------|
| **API First** | API spec finalized, both sides ready | PHP backend + Frontend |
| **Frontend Split** | Large page with distinct layout vs. logic work | Layout agent + JS/logic agent |
| **Multi-Page** | 2+ independent pages need implementation | One agent per page |
| **Full-Stack 3-Way** | New feature from scratch, DB not yet designed | DB → then API + Frontend |

## Core Dispatch Steps

1. **Define the shared contract** — Write API spec, DB schema, or component interface before dispatching.
2. **Verify independence** — Confirm agents will not write to the same files.
3. **Write focused agent prompts** — Each prompt: scope, shared context, deliverable, constraints.
4. **Dispatch in parallel** using the Agent tool (multiple calls in a single message).
5. **Integrate** — Read each agent's summary, check for conflicts, test the integration.

## Integration Checklist

After all agents return:
- [ ] No two agents modified the same file
- [ ] API endpoint names/methods match between PHP and frontend
- [ ] DB column names match API field names match frontend variable names
- [ ] Error handling paths are consistent across layers
- [ ] Run the application and test the happy path end-to-end

## Full Prompt Templates

For complete agent prompt templates per pattern, and shared context blocks:
→ Read `references/dispatch-patterns.md`
