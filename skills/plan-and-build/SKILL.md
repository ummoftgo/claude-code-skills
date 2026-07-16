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
2. **Current context** — record the relevant architecture, constraints, and files inspected.
3. **Specification** — define behavior, interfaces or data contracts, error cases, and acceptance criteria.
4. **Implementation plan** — list ordered steps with likely files and verification for each step.
5. **TDD decision** — state whether tests will be written first and why.
6. **Parallelization decision** — identify independent workstreams or state why the work remains sequential.
7. **Design approval decision** — state whether the change requires the checkpoint below and why.

Keep the artifact short enough to guide implementation. Pause for the user when an unresolved choice would materially change behavior, schema, external integration, or scope. Design and parallel execution have the explicit approval requirements below.

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

## 5. Finish with evidence

Run the focused tests, relevant wider tests, and project checks appropriate to the risk. Report:

- what was implemented;
- where the specification and plan live;
- which tests were written first or why TDD was skipped;
- which workstreams ran in parallel or why execution stayed sequential;
- verification results and any remaining risk.
