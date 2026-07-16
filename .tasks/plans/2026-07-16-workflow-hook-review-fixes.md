# Workflow Hook Review Fixes

## Goal and non-goals

Apply the four actionable findings from the 2026-07-15 follow-up review: preserve symlink-managed JSON settings, preserve unrelated empty hook groups, detect disabled Codex hooks before installation, and cover the core Korean planning-reminder prompts. Do not redesign the skill workflow, change hook output contracts, or modify unrelated pre-existing dirty skill files.

## Current context

- `hooks/workflow_hook_config.py` atomically replaces the path passed to it, which detaches a settings symlink.
- `_without_managed()` drops every empty hook group, even when it did not contain the managed command.
- `install.sh` checks Codex inline hook conflicts but not `[features] hooks = false`.
- `hooks/workflow-reminder.py` misses realistic wording for an existing TDD project and several independent tasks.
- Claude Code and Codex hook input/output contracts were verified in the preceding review.

## Specification

1. Read and atomically update the resolved target of a settings symlink while leaving the symlink in place. Reject dangling settings symlinks instead of replacing them.
2. Remove an empty hook group only when removing the managed command made that group empty; preserve unrelated groups that were already empty.
3. Parse enough TOML to identify an effective `[features] hooks = false` setting without adding a third-party dependency. Before installing a Codex hook, warn and default to skipping when hooks are disabled. Preserve existing `config.toml`.
4. Remind for at least these prompts: `프로젝트를 새로 작성해줘`, `기존 TDD 프로젝트에 결제 기능 코드를 작성해줘`, and `독립적인 페이지 3개를 각각 작성해줘`.
5. Preserve all existing passing behavior and installation ownership safeguards.

## Implementation plan

1. Add focused failing tests in `tests/test_workflow_hook_config.py` and `tests/test_workflow_reminder.py`.
2. Update path resolution and hook-group filtering in `hooks/workflow_hook_config.py`.
3. Add a Codex hook-availability status action and wire it into `install.sh`.
4. Expand the substantial-work expressions in `hooks/workflow-reminder.py`.
5. Update `INSTALL.md`, run focused tests, the full suite, shell syntax checks, skill validation, and `git diff --check`.

## TDD decision

Use TDD. Each reported defect has a small deterministic reproduction, and the repository already has focused unit and shell integration tests for these files. Confirm the new tests fail for the intended reasons before changing production code.

## Parallelization decision

Keep the work sequential. The config helper, installer branch, and their shell integration tests share one contract and overlapping files; parallel edits would add merge and sequencing risk. No user approval for parallel dispatch is needed because no workers will be dispatched.

## Design approval decision

No new checkpoint is needed. The user explicitly approved proceeding from the prior review, and these are narrow corrections to the already approved design rather than new architecture, persistence, API, or external-integration choices.

## Acceptance criteria

- A settings symlink remains a symlink and its target receives the JSON update.
- A dangling settings symlink produces a safe error and is not replaced.
- An unrelated empty hook group survives install/remove operations.
- Codex installation defaults to skip when `[features] hooks = false` is effective.
- The three reviewed Korean prompts produce a reminder.
- All prior tests and validation commands pass.
