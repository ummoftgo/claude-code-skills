---
name: plan-and-build
description: "Plan and execute substantial new code work with a lightweight specification, implementation plan, proportionate verification, and safe parallel task split. Use when creating a new project, adding a feature or other non-trivial new code, or handling multiple implementation tasks that may be independent. Do not use for small localized edits, read-only review or explanation, pure research, or routine maintenance with an already-obvious change."
---

# Plan and Build

Use a lightweight workflow for substantial implementation. Keep the process proportional to the task; do not turn a clear feature into ceremony.

## 1. Confirm the workflow is warranted

Inspect the repository instructions and relevant code before deciding.

- Continue with this workflow for a new project, a new feature, substantial new behavior, a cross-layer change, or several implementation tasks.
- Exit the workflow and make the change directly when it is a small localized edit with an obvious solution.
- Do not use this workflow for read-only review, explanation, research, translation, or status reporting.
- Preserve the user's explicit scope, paths, constraints, and requested level of autonomy.

## 2. Write the specification and plan

Before editing implementation code, create one concise planning artifact. Follow an existing project convention when present; otherwise use `.tasks/plans/{yyyy-mm-dd}-{slug}.md`.

Include:

1. **Goal and non-goals** — state the observable outcome and boundaries.
2. **Current context** — record the relevant architecture, constraints, and files inspected. **Separate what you confirmed from what you are assuming**, and for each assumption name the external dependency behind it and which requirements or steps break if it turns out false. An assumption that still needs an answer does not belong here as settled fact — send it to `## Clarifications` or `## Deferred` below.
3. **Specification** — define behavior, interfaces or data contracts, error cases, and acceptance criteria.
4. **Implementation plan** — list ordered steps with likely files and verification for each step.
5. **Verification strategy** — choose the checks, any new tests, and whether a specific part benefits from test-first work; give a brief reason.
6. **Parallelization decision** — identify independent workstreams or state why the work remains sequential.
7. **Design approval decision** — state whether the change requires the checkpoint below and why.

Keep the artifact short enough to guide implementation. Pause for the user when an unresolved choice would materially change behavior, schema, external integration, or scope. Design and parallel execution have the explicit approval requirements below.

### Resolve ambiguity before planning further

Run this scan once, after the goal is clear and before the specification hardens. It exists
because the single instruction "pause when a choice would materially change scope" gives no
way to tell *which* unknowns are worth a question.

Score each category **Clear / Partial / Missing**. Keep the map to yourself; show it only when
you end up asking nothing.

| # | Category | Covers |
|---|---|---|
| 1 | Scope and non-goals | What is explicitly out; which user roles differ |
| 2 | Data and state | Entities, relationships, identity, **lifecycle** (retention, expiry, deletion), state transitions, migration, rollback, old/new coexistence |
| 3 | Interface contract | Request/response shape, error format, the boundary between callers, version compatibility, deployment order |
| 4 | Auth, permission, and trust boundary | Who may call it, what input is trusted, **and what the response exposes** |
| 5 | Failure and edges | Errors, empty and loading states, concurrency, timeout, retry, idempotency, recovery |
| 6 | Measurable completion | Whether each acceptance criterion can actually be checked; performance limits when relevant |
| 7 | Unresolved markers | TODOs, placeholders, and vague adjectives used without a number |

Check these only when the trigger fits: user-facing UI → accessibility · an existing localized
surface → i18n · async work or an external integration → observability (who notices the failure).

**Compliance is not a standing scan category here.** Ordinary data lifecycle — retention,
expiry, deletion — always belongs to category 2 above. What is excluded is the separate
compliance layer: *legally or contractually mandated* retention periods, deletion requests,
consent, data residency, and audit trails. Those have not come up in this repository's work, and
a check that never fires is dead weight in a scan run on every plan. When a task does carry a
stated legal or contractual obligation, record it in `Current context` as an external constraint
and turn it into an acceptance criterion — do not assume the auth and permission category covers
it, because it does not.

Then:

1. Rank the Partial and Missing categories by **impact × uncertainty** and carry **at most five
   questions** forward. Set aside anything that would not change implementation or verification,
   and anything that can safely wait for the plan itself — set aside means recorded under
   `## Deferred`, not silently dropped.
2. **Ask dependent questions one at a time; group independent ones two or three together.** Lead
   each with a recommendation and the reason for it, so the user can accept rather than compose.
3. Recompute after each round. **Stop as soon as the deciding uncertainty is resolved** — the
   limit of five is a ceiling, not a quota.
4. Whatever remains unasked goes under `## Deferred` with what it blocks. Not asking is not the
   same as being clear, and only the written record keeps those apart.
5. Record answers under `## Clarifications` as `- Q: … → A: …`, then fold each into the
   requirement it affects. Where an answer contradicts an earlier line, **replace that line**
   rather than adding a second one.

Use a structured question tool when the environment has one; otherwise ask in plain text. The
contract is the shape — a recommendation with each question, at most five, dependent questions
sequential, early exit, and the leftovers written down — not any particular tool.

This scan runs *inside* the workflow. The scope gate in §1 comes first: a small localized edit
with an obvious answer leaves the workflow entirely and never reaches this table.

### Identify requirements when the work needs tracing

Most plans do not need this. Prose requirements are enough when one person implements one
feature in one sitting. Give requirements stable identifiers **only** when at least one holds:

- several requirements must be verified independently and mapped to implementation steps;
- there are multiple workstreams or parallel work;
- architecture, API, schema, storage, or an external integration changes;
- the work is handed across sessions or people, or a plan-versus-code audit is expected later.

When it applies:

```
FR-001: <functional requirement>
SC-001 (verifies FR-001) — 검증: <observable, checkable method>
구현 단계 N: <description> — covers: FR-001 — 검증: <command / test>
```

- Implementation steps carry **`covers:` only**. §2 item 4 already requires verification per
  step, so a second `verifies:` label would restate it.
- Each `SC` declares **how it is checked**. A success criterion whose check cannot be written is
  not measurable, and that shows up here rather than at the end.
- **Every active `SC`'s declared check must be assigned to the verification of at least one step
  that `covers:` its `FR`.** Without this an `SC` can have a method that no step ever runs — say
  `SC-002` is "100 rows rejected within 3s" while the only step covering its `FR` lists a plain
  functional test. The form passes; the load check never happens.
- `SC` must be **observable and checkable**, not technology-free. A performance ceiling, a
  compatibility version, or a failure mode is a legitimate criterion for internal API,
  migration, or build work. The one rule that always holds: **no vague adjective without a
  number** — fast, scalable, secure, intuitive, robust.
- **Lifecycle:** never renumber and never reuse an identifier. A withdrawn requirement keeps its
  line with a `withdrawn` status instead of disappearing, and is excluded from missing-work
  counts — it is not an unbuilt requirement, so an audit must not report it as one.
- **Readable form:** an identifier that reaches the user — in a plan summary, a status report, or
  a question asking them to decide — needs a label a person can read. Invoke `readable-ids` if it
  is installed to register the identifier and render it as `FR-001(feature/label)`. Without that
  skill, keep a label beside every identifier in the plan itself; a bare `FR-001` in a sentence
  costs the reader a document lookup that the writer could have spent one phrase avoiding.
- Identifiers make gaps visible and give an audit an anchor to compare against `file:line`
  evidence. They do not make coverage mechanical — **do not claim "100% coverage"**; a `covers:`
  label is a starting point for judgement, not proof.

### Design approval checkpoint

Before editing implementation code, present a recommended design with concise alternatives and trade-offs, then wait for explicit user approval when any of these apply:

- a new project is being created;
- architecture, persistence, API/schema contracts, or external integrations materially change;
- multiple viable approaches differ meaningfully in scope, cost, compatibility, or operational risk.

Use one approval checkpoint for the overall direction rather than approval after every section. When none of these conditions apply and the design is straightforward, record why no checkpoint is needed, share the plan summary, and continue without another prompt. A user who already explicitly approved the same proposed design does not need to be asked again.

## 3. Choose proportionate verification

Choose verification per changed behavior, not once for every file or for the entire project. Honor explicit user requirements and applicable project checks. Separate three decisions: what evidence is sufficient, whether a new permanent test is needed, and whether writing it first adds value.

| Change | Default approach |
|---|---|
| Documentation, wording, formatting, or a reversible low-impact edit | Use relevant existing checks or direct inspection; no new test or TDD cycle by default. A changed executable/configuration contract still needs its relevant checks. |
| Straightforward wiring or ordinary new behavior | Implement, then use existing tests or a focused runtime/integration check. Add coverage only for a meaningful gap. |
| Calculations, parsing, authorization, state transitions, or other consequential branching | Add focused behavioral coverage where missing. Prefer TDD when an inexpensive failing test clarifies the contract or guards a likely failure. |
| Reproduced bug | Reuse the failing test or reproduction. Add a regression test when it provides lasting protection at reasonable cost. |
| Explicit test-first requirement | Apply TDD within the requested scope. |

A new project or an existing test runner alone does not select TDD. Judge regression risk, existing coverage, and setup/maintenance cost. Do not build test infrastructure for a trivial edit or add tests that merely mirror implementation details or pin prose wording. Keep permanent tests for stable behavior or contracts; temporary probes need not become repository files. For risky legacy changes, characterization tests may be the appropriate starting point; when isolation is disproportionately expensive, use focused runtime evidence and disclose its limits.

When TDD is selected, group related acceptance, failure, and boundary cases into one focused feature-level batch. Confirm failure for the expected behavioral reason, implement the coherent change, then run that batch. An existing relevant failure already supplies the red evidence; do not break working code or repeat a separate red-green cycle for each helper or assertion. Refactor only as needed for the requested change.

Run wider checks when affected dependencies, integration, or project requirements warrant them, normally after the related changes are complete. Once the chosen checks pass, stop testing unless subsequent changes, failures, changed inputs/environment, or a specific unresolved concern justify another run. Do not add a reviewer or another suite merely to reconfirm success.

When test or application code depends on a library, framework, SDK, API, CLI, or cloud service, invoke `use-context7` first if it is installed.

## 4. Split independent work

Build a small dependency graph from the implementation plan. Stabilize shared contracts before dispatching work.

Parallelize only when all are true:

- At least two workstreams are meaningful and independent.
- Each workstream has a disjoint file scope or an explicit ownership boundary.
- No workstream needs another workstream's unfinished output.
- Shared API, schema, component, or data contracts are already written.
- Agent or parallel execution tools are available.

Keep work sequential when scopes overlap, requirements are unsettled, or integration risk outweighs the time saved. For web backend/frontend splits, invoke `web-parallel-dispatch` if installed.

Before dispatching parallel workers, state their responsibilities, file ownership boundaries, shared contracts, and why the split is safe. Reuse an explicit request for parallel execution, earlier approval for this scope, or applicable project instructions that permit parallel execution. When that authorization covers the proposed split, announce the split and proceed without asking again. An implementation request alone is not parallel authorization. If no existing authorization covers the split, ask whether to proceed and wait for explicit user approval; continue independent work that does not depend on that answer. Reopen the decision only when the split introduces a material scope, cost, or operational-risk change beyond the existing authorization. When work remains sequential, record the reason and continue.

Use the fewest workers that make useful independent progress, respect the runtime's concurrency limit, and keep working on an independent part while they run. Inherit the session's model and reasoning settings unless the user or project explicitly selects others; this skill does not prescribe model IDs or a universal effort level.

Give each worker:

- the relevant specification and shared contract;
- exact files or directories it may edit;
- explicit files it must not edit;
- its verification strategy, existing evidence, and ownership of any new tests;
- the expected summary and any assumptions it must report.

After workers finish, inspect every diff, check for overlaps and contract mismatches, and integrate centrally. Reuse valid worker results and run the checks needed for the combined behavior; isolated success does not cover a newly connected boundary.

## 5. Update the plan when implementation diverges

Implementation reveals what planning could not. When any of these turns out materially different
from what §2 recorded, **update the same planning artifact rather than letting the plan and the
code drift apart**:

- an assumption or its external dependency;
- an active `FR`/`SC`, including one that should now be `withdrawn`;
- an API, schema, storage, or external-integration decision;
- file ownership between parallel workstreams;
- the verification strategy for a step.

Re-run the ambiguity scan only for the categories the change touches — a storage change reopens
§2 and §5 of that table, not all seven. Ask for approval again **only when the change crosses the
design approval boundary above**; a smaller correction is recorded and carried on with.

A plan that silently stops describing the code is worse than no plan: the next reader, the
handoff, and any later plan-versus-code audit all take it as current intent.

## 6. Finish with evidence

Use the verification strategy from §3 and report its completed evidence; this is not a separate test pass. Report:

- what was implemented;
- where the specification and plan live;
- the verification used, including any coverage added and material gaps;
- which workstreams ran in parallel or why execution stayed sequential;
- verification results and any remaining risk;
- anything left under `## Deferred`, and what it leaves unsettled.
