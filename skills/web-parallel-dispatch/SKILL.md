---
name: web-parallel-dispatch
description: "Dispatch independent web implementation work to subagents with explicit file ownership and shared contracts. Use for substantial backend/frontend splits, independent pages, or separate UI layout and logic. Reuse user or project authorization for parallel execution; ask only when the proposed split is not already authorized."
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
2. **Query library docs first** — If the `use-context7` skill is installed, invoke it now.
   Query the relevant framework docs for each layer about to be implemented
   (e.g., Svelte runes for a frontend agent, PDO for a PHP backend agent).
   Use the exact skill name: `use-context7`.
3. **Verify independence** — Confirm agents will not write to the same files.
4. **Resolve authorization** — Present the proposed workers, responsibilities, file ownership boundaries, shared contract, and why the split is safe. Reuse an explicit request for parallel execution, earlier approval for this scope, or applicable project instructions permitting parallel work. When that authorization covers the split, proceed without another question. An implementation request alone is not parallel authorization. Otherwise ask whether to proceed in parallel and wait for explicit user approval; continue independent work that does not depend on that answer. Ask again only for a material scope, cost, or operational-risk change beyond the existing authorization.
5. **Write focused agent prompts** — Each prompt: scope, shared context, deliverable, constraints.
6. **Dispatch in parallel** using the available subagent tool within that authorization. Use only as many workers as have substantial independent work, respect the runtime concurrency limit, and keep the lead agent working on an independent part. Inherit model and reasoning settings unless the user or project explicitly selects others.
7. **Integrate** — Read each agent's summary, check for conflicts, test the integration.

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
