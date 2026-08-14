---
name: plan-and-build
description: "Plan and execute substantial new code work with a lightweight specification, implementation plan, TDD decision, and safe parallel task split. Use when creating a new project, adding a feature or other non-trivial new code, or handling multiple implementation tasks that may be independent. Do not use for small localized edits, read-only review or explanation, pure research, or routine maintenance with an already-obvious change."
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
5. **TDD decision** — state whether tests will be written first and why.
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
- Identifiers make gaps visible and give an audit an anchor to compare against `file:line`
  evidence. They do not make coverage mechanical — **do not claim "100% coverage"**; a `covers:`
  label is a starting point for judgement, not proof.

### Design approval checkpoint

Before editing implementation code, present a recommended design with concise alternatives and trade-offs, then wait for explicit user approval when any of these apply:

- a new project is being created;
- architecture, persistence, API/schema contracts, or external integrations materially change;
- multiple viable approaches differ meaningfully in scope, cost, compatibility, or operational risk.

Use one approval checkpoint for the overall direction rather than approval after every section. When none of these conditions apply and the design is straightforward, record why no checkpoint is needed, share the plan summary, and continue without another prompt. A user who already explicitly approved the same proposed design does not need to be asked again.

## 3. Decide whether TDD fits

Treat TDD as a deliberate choice, not an automatic requirement. Prefer it when the behavior can be expressed with a focused test at reasonable cost and either condition holds:

- The project is new and incremental behavior tests will provide useful design feedback. Establish only the smallest appropriate test foundation.
- The existing project explicitly follows a TDD or test-first convention for nearby behavior.

The mere presence of a test runner or test directory does not require TDD. Consider coupling, legacy constraints, integration cost, and the value of a failing-first test. Record the decision and rationale in the planning artifact.

When TDD is selected, follow red-green-refactor:

1. Write the smallest test that expresses one acceptance criterion.
2. Run it and confirm it fails for the expected reason.
3. Implement only enough production code to pass.
4. Run the focused test, then the relevant wider suite.
5. Refactor while keeping tests green.

When TDD is not the best fit, use the strongest proportionate alternative: characterization tests before risky legacy changes, tests alongside or immediately after implementation, focused integration tests, or explicit runtime verification. Do not force TDD onto generated files, documentation-only changes, formatting, exploratory spikes explicitly intended to be discarded, or behavior that cannot be isolated without disproportionate infrastructure.

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

Before dispatching any parallel workers, present the proposed workstreams to the user, including their responsibilities, file ownership boundaries, shared contracts, and why parallel execution is safe. Ask whether to proceed in parallel and wait for explicit user approval. Do not spawn workers or begin parallel edits before that approval. When the work remains sequential, record the reason and continue without an additional approval prompt.

Give each worker:

- the relevant specification and shared contract;
- exact files or directories it may edit;
- explicit files it must not edit;
- its test responsibility and verification command;
- the expected summary and any assumptions it must report.

After workers finish, inspect every diff, check for overlaps and contract mismatches, integrate centrally, and run the combined verification. Never treat successful isolated work as proof that the integrated result works.

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

Run the focused tests, relevant wider tests, and project checks appropriate to the risk. Report:

- what was implemented;
- where the specification and plan live;
- which tests were written first or why TDD was skipped;
- which workstreams ran in parallel or why execution stayed sequential;
- verification results and any remaining risk;
- anything left under `## Deferred`, and what it leaves unsettled.
