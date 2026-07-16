# Lightweight Superpowers Completion

## Goal and non-goals

Complete the lightweight Claude Code/Codex workflow with the high-value gaps found in review: proportional design approval, consistent approval before write-heavy parallel work, systematic debugging, and safer Codex hook installation. Do not recreate Superpowers' mandatory worktrees, universal TDD, per-task agents, review loops, or automatic branch finishing.

## Current context

- `plan-and-build` already writes a specification and plan, decides whether TDD fits, and requires approval before its own parallel dispatch.
- `web-parallel-dispatch` can currently dispatch without that approval.
- Claude and Codex both support reusable skills and `UserPromptSubmit`; the reminder remains advisory rather than blocking.
- Codex merges `hooks.json` with inline `config.toml` hooks and warns when both representations exist in one layer.

## Specification

1. Require one explicit design approval before implementation only for new projects or material architecture, schema, API, external integration, or competing-direction decisions. Record when no checkpoint is needed.
2. Require explicit approval inside `web-parallel-dispatch` before spawning write-capable workers.
3. Add a concise `systematic-debugging` skill for unclear, intermittent, cross-layer, or repeatedly misfixed bugs. It must reproduce and prove root cause before editing, preserve read-only diagnosis scope, add regression protection where practical, and verify the final fix.
4. Install and remove the new skill for both Claude Code and Codex and document it.
5. Stop writing the ignored Claude `UserPromptSubmit` matcher.
6. Detect real inline Codex hook event tables while ignoring `[hooks.state.*]` trust records. Warn and default to skipping `hooks.json` installation unless the user explicitly continues.

## Implementation plan

1. Add failing regression tests for inline-hook detection, matcher-free hook entries, and the updated reminder contract.
2. Update the hook configuration helper and installer contract.
3. Update `plan-and-build` and `web-parallel-dispatch` approval rules.
4. Initialize and write `systematic-debugging`, then add install/uninstall and documentation entries.
5. Run unit tests, shell/Python syntax checks, skill validation, and diff checks.

## TDD decision

Use test-first changes for hook/config behavior because the repository already has focused tests and the expected failures are cheap to express. Validate Markdown skill behavior structurally and by direct instruction review; no runtime unit test can prove model judgment reliably.

## Parallelization decision

Keep execution sequential. The installer, helper, skill lists, and documentation share ordering and naming contracts. The user approved the feature set but did not approve parallel worker execution.

## Design approval

The user explicitly approved the four recommended enhancements from the preceding review, so no additional design checkpoint is required for this implementation.

## Acceptance criteria

- Existing foreign hooks remain preserved.
- Trust-state tables do not trigger an inline-hook warning; actual inline hook event tables do.
- Generated Claude and Codex `UserPromptSubmit` entries omit `matcher`.
- Both clients receive `systematic-debugging` through the existing installer flow.
- All existing and new tests and validators pass.
