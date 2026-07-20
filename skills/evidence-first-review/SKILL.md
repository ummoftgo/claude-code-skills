---
name: evidence-first-review
description: "Perform evidence-grounded read-only reviews that lock user-supplied context and scope before independently verifying current designs, code, diffs, files, raw JSON/CSV/database data, and runtime results. Use for context-first design/code/data reviews, explicit no-change audits, rechecks of prior findings, second or final reviews, final approval decisions, and direct inspection of non-Git directories. Do not use for an ordinary first-time PR or branch merge review; use branch-merge-review instead."
---

# Evidence-First Review

Review the requested scope without changing it. Treat supplied documents as statements of intent and current artifacts as the evidence needed to confirm or refute those statements.

## 1. Lock context, scope, and constraints

Before evaluating claims:

1. Record the user's language, requested output format, explicit context files, paths, revision or current-file scope, and read-only constraints.
2. Read every explicitly supplied context file before exploring broader repository material.
3. Keep findings within the locked scope unless a cross-cutting dependency is necessary to prove impact. Explain any such expansion.
4. In a non-Git directory, inspect the current files directly; do not require a diff or repository history.
5. For a recheck, locate prior findings in the conversation, user-designated documents, or the locked repository scope. Ask for their location only when none can be found, because a recheck cannot classify missing findings reliably.

Do not let a context document prove its own claims. Verify it independently against the current code, diff, source data, configuration, or runtime behavior.

For an ordinary initial PR or branch merge review, stop and use `branch-merge-review`. Use this skill when evidence-first, explicit read-only, historical-finding, raw-data, non-Git, or approval-oriented behavior is central to the request.

## 2. Select one review mode

Choose the mode from the user's requested outcome and state it in the report.

| Mode | Use it for | Required result |
|---|---|---|
| `initial` | Discovering new problems in the current design, code, or data | Evidence-backed findings and a scope-level verdict |
| `recheck` | Verifying a second review, prior report, or named findings | Classify every prior finding as `resolved`, `partially resolved`, `unresolved`, or `regressed`; list new findings separately |
| `final-approval` | Revalidating must-fix conditions before sign-off | Recheck every required condition and decide `approved`, `conditionally approved`, or `hold` |

Do not silently drop a prior finding. Preserve its identity, cite the current evidence, and explain why its status changed or stayed the same.

## 3. Build an evidence ledger

Use the strongest available sources in this order:

1. Current source files and configuration at exact locations.
2. The relevant current diff or revision range when Git exists and history is part of the scope.
3. Raw JSON, CSV, database rows, generated indexes, or other source records parsed or queried directly.
4. Runtime output produced with the version and command required by project manifests.
5. Context documents, summaries, and comments as intent or supporting explanation.

For raw-data claims, record the parser or read-only query, relevant counts, field names, and representative counterexamples. For runtime claims, record the command, runtime version, and result. Prefer manifest-selected PHP, Node, or other versioned tools over system defaults.

For each conclusion:

- cite `file:line`, a record key or row, or the exact runtime observation;
- distinguish direct observation from inference;
- look for disconfirming evidence and concrete counterexamples;
- state uncertainty when the available artifacts cannot prove the claim;
- avoid reproducing secrets or unnecessary personal data in the report.

Use installed tools only. Do not weaken verification by silently substituting an incompatible runtime.

## 4. Enforce the read-only boundary

This workflow is non-mutating. When the user explicitly says read-only, no changes, or an equivalent constraint, treat these rules as absolute even if another workflow normally writes a report:

- Do not create or modify files, including report files and generated artifacts.
- Do not install tools or dependencies.
- Do not create checkouts or worktrees or switch revisions in a way that changes the workspace.
- Do not stage changes, commit, push, or alter Git state.
- Do not apply fixes while reviewing.
- Return the result in the user's language as a message only.

Read-only diagnostic commands are allowed when they stay within the requested scope. If a required check needs a write or a missing tool, report the limitation instead of expanding authority.

## 5. Execute the selected mode

### `initial`

Trace each requirement or claim to current evidence, test likely failure boundaries, and report only reproducible or well-supported problems. Separate confirmed findings from open questions.

### `recheck`

Create a one-to-one ledger of prior findings. Reproduce the original condition against current artifacts, classify it, and cite what changed. After all prior findings are accounted for, run a bounded pass for new regressions and list those findings separately.

### `final-approval`

Translate must-fix requirements into explicit checks. Re-run each check against current artifacts and runtime evidence. Use `conditionally approved` only when remaining conditions are concrete, bounded, and do not invalidate the approval target; otherwise use `hold`.

## 6. Report with traceable evidence

Read [references/report-format.md](references/report-format.md) before writing the final report. The user's requested format always takes precedence.

When no format is supplied, include severity, `file:line` or data location, evidence, impact, a concrete recommendation, and the final verdict. Write all prose in the user's language while preserving code identifiers, paths, commands, and quoted evidence in their original form.
