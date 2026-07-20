---
name: safe-checkpoint
description: "Create safe, scoped Git checkpoints and resumable handoffs. Use when the user asks to commit only specified or current changes, make a checkpoint, finish before leaving work, continue from another place or later, or prepare or update a handoff. Inspect branch, upstream, status, diff, runtime manifests, and existing handoff sources first; separate intended changes, unrelated dirty work, and generated or intentionally preserved files; enforce separate authority for handoff writes, staging and commit, remote push, and failed WIP commits."
---

# Safe Checkpoint

Preserve the user's intended work without absorbing unrelated changes. Do not infer write authority from a request to inspect, verify, hand off, commit, or push; each action has its own boundary.

## 1. Inspect before changing Git or handoff state

Read, without mutating:

- repository root, current branch or detached state, configured upstream, and recent relevant commits;
- staged, unstaged, and untracked status plus the actual diff for each category;
- project runtime manifests and existing verification commands;
- user-named handoff material and repository conventions for progress, resume, or handoff documents.

Classify every dirty path as:

1. current request scope;
2. pre-existing or unrelated dirty work;
3. generated output or an intentionally preserved change.

Do not stage while this classification is uncertain. If the requested scope cannot be established from the conversation and current diff, present the exact candidate file list and ask the user to confirm it before staging.

## 2. Enforce action-specific authority

Do not infer write authority across rows.

| Action | Required authority |
|---|---|
| Inspect status, diffs, manifests, and run existing verification | Included in a checkpoint request |
| Create or update a handoff document | An explicit request to write or update the handoff |
| Stage and commit | An explicit commit request |
| Push to a remote | An explicit push request |
| Create a failed WIP checkpoint | An explicit WIP or leaving-work checkpoint request, or separate approval |

A commit request does not authorize a push. A handoff request does not authorize staging. A request to report checkpoint scope does not authorize any write.

## 3. Resolve the handoff source of truth

When a handoff path is supplied, use that path. Otherwise:

1. Search the locked repository scope for documented handoff, progress, or resume conventions.
2. If exactly one current source of truth exists, update it only when handoff writing is authorized.
3. If none exists, create `.tasks/handoffs/YYYY-MM-DD-{slug}.md` only when the user explicitly requested a handoff document.
4. If multiple plausible sources exist, show the candidates and ask the user to choose before writing.

Read [references/handoff-template.md](references/handoff-template.md) before creating or updating a handoff. Preserve an established repository format when it carries the same information.

## 4. Verify with the project runtime

Inspect runtime manifests before choosing commands, including `composer.json`, `package.json`, lockfiles, toolchain files, and repository scripts. Prefer the PHP, Node, or other runtime version required by those manifests. Do not install missing verification tools unless the user separately authorizes installation.

Run the focused checks for the intended paths, then the relevant wider checks in proportion to risk. Record exact commands and results for the handoff and final report.

- For a normal commit request, stop before staging and commit when required verification fails.
- For an explicitly authorized failed WIP checkpoint, record the failure, evidence, and exact resume point in the handoff, then allow a commit whose subject begins with `wip:`.
- Never convert an ordinary failed commit into WIP without authority.

## 5. Stage and commit only the intended scope

After successful verification or explicit failed WIP authority:

1. Stage explicit intended paths rather than using broad staging that can absorb unrelated work.
2. Inspect the staged file list and staged diff.
3. Confirm unrelated dirty changes, secrets, generated files, and local configuration are excluded unless explicitly intended.
4. Commit with a subject that describes the checkpoint; use `wip:` only for an authorized failed WIP checkpoint.
5. Read the resulting HEAD and remaining dirty state.

Do not clean up, reset, stash, rewrite, or include unrelated changes merely to make the worktree look clean.

## 6. Push only when requested

Before a remote push, confirm the target branch, remote, and upstream relationship. Do not force-push or rewrite history without explicit authority.

After pushing, re-read:

- local HEAD and remote/upstream HEAD;
- upstream synchronization or ahead/behind state;
- staged, unstaged, and untracked paths that remain.

Treat the push as complete only when the intended remote state is confirmed.

## 7. Leave a resumable handoff and final report

An authorized handoff must record:

- branch and checkpoint commit;
- completed work and remaining work;
- verification commands and results, including failures;
- exact commands or entry points needed to resume;
- every intentionally dirty or generated path and why it remains;
- artifact hashes only when needed for identity or reproducibility.

When a handoff is part of the checkpoint commit and cannot contain its own hash, identify the checkpoint as `pending (this handoff is included in the checkpoint commit)` and report the actual resulting HEAD in the final response. Do not create extra history solely to embed a self-referential hash.

Finish by reporting the branch, resulting commit, push/upstream state, verification evidence, handoff path if written, and all remaining dirty files. Never claim a clean or synchronized state without re-reading it.
