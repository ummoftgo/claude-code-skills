---
name: evidence-first-review
description: "Perform evidence-grounded read-only reviews that lock the user's context and scope, then independently verify current designs, code, diffs, files, raw JSON/CSV/database data, and runtime results. Work mode decides before scope: use this skill whenever the request is a recheck of prior findings, a second or final review, a final approval or sign-off decision, evidence-first verification of specific claims, or direct inspection of raw data or a non-Git directory — including when the scope is a PR, branch, or merge diff ('이 PR의 이전 지적을 재검토하고 최종 승인해줘'), because branch-merge-review has no recheck or approval mode. Only for an ordinary first-time review does scope decide: a PR, branch, or merge diff belongs to branch-merge-review. A read-only or no-changes constraint selects neither skill; it only constrains how the selected one runs, so '수정하지 말고 브랜치 리뷰해줘' runs branch-merge-review read-only."
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

Work mode decides before scope. When the request is a `recheck` of prior findings, a `final-approval` verdict, or evidence-first verification of specific claims, raw data, or a non-Git directory, use this skill even if the scope is a PR, branch, or merge diff: `branch-merge-review` has no such mode and would return newly discovered findings instead of the per-finding statuses and approval verdict the user asked for. Only when the mode is `initial` does scope decide — then an ordinary first-time PR or branch merge review belongs to `branch-merge-review`, so stop and use it. A read-only or no-changes constraint changes neither axis; it only constrains how the selected skill runs, so '수정하지 말고 브랜치 리뷰해줘' is a first-time branch-scoped review that runs `branch-merge-review` read-only.

## 2. Select one review mode

Choose the mode from the user's requested outcome and state it in the report.

| Mode | Use it for | Required result |
|---|---|---|
| `initial` | Discovering new problems in the current design, code, or data | Evidence-backed findings and a scope-level verdict |
| `recheck` | Verifying a second review, prior report, or named findings | Classify every prior finding as `resolved`, `partially resolved`, `unresolved`, or `regressed`; list new findings separately |
| `final-approval` | Revalidating must-fix conditions before sign-off | Recheck every required condition and decide `approved`, `conditionally approved`, or `hold` |

Do not silently drop a prior finding. Preserve its identity, cite the current evidence, and explain why its status changed or stayed the same.

### `plan-conformance` profile

A profile is not a fourth mode. It fixes **what the ledger is made of**, leaving the mode above
to decide what the review has to produce. Where `recheck` builds its ledger from prior findings,
`plan-conformance` builds it from the requirements of a plan.

Apply it when the user asks whether a named plan, specification, or design was actually built —
"이 계획대로 구현됐는지 검증해줘", "사양 대비 빠진 구현을 찾아줘". Lock the plan path and the
revision or working-tree scope with the §1 procedure first; ask for the path when more than one
plan could be meant.

**Judge authority before conformance.** Every requirement is first `active`, `withdrawn`, or
`superseded` — a requirement the user has since dropped or replaced is not a missing
implementation, and calling it one sends people to rebuild something deliberately abandoned.
Only `active` requirements then take `implemented` / `partial` / `missing` / `unverifiable`.

Report as a table keyed by requirement identifier — or by quoted requirement text when the plan
has no identifiers — with `file:line` evidence for every row. Behaviour found in the reviewed
scope that no requirement asked for is listed separately as `unrequested`: it may be scope
creep, an undocumented decision, or something the plan simply never recorded. **Do not call it
dead code**, and do not recommend deleting it on the strength of its absence from the plan.

The plan is intent, never proof. It can be stale, or contradicted by a later instruction from
the user — §1's rule that a context document cannot establish its own claims applies to it in
full. **Do not modify the plan file.** Report inline; adding the gaps back into the plan is
`plan-and-build`'s §5, run with its own authority.

When this profile runs alongside `recheck` or `final-approval`, it **adds** a ledger rather than
replacing one. Prior findings keep their one-to-one tracking, and the two ledgers cross-reference
where they touch the same code.

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
