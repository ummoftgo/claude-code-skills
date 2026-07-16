# Workflow Hook Scope Safety

## Goal and non-goals

Close the three remaining workflow-hook safety gaps found in the follow-up review: prevent silent writes through settings symlinks outside the selected install scope, recognize all Codex settings that disable user/project hooks, and stop uninstallation safely when the settings symlink is dangling. Do not redesign the reminder skill, change hook matching behavior, or modify unrelated dirty skill files.

## Specification

1. Resolve a JSON settings path once per helper operation. When an allowed root is supplied, reject a resolved target outside that root unless the caller passes an explicit outside-root override.
2. Make the installer and uninstaller pass `INSTALL_BASE_DIR` as the allowed root. If a valid settings symlink resolves outside that root, explain the target and require a default-no confirmation before continuing.
3. Treat a dangling settings symlink as an invalid configuration during both install and removal. Never remove the installed hook file while its configuration cannot be inspected safely.
4. Detect these Codex states and report the concrete reason: `[features] hooks = false`, deprecated `[features] codex_hooks = false` when the canonical key is absent, and top-level `allow_managed_hooks_only = true`.
5. Preserve valid in-scope symlinks, atomic target updates, foreign hook entries, and existing ownership safeguards.

## Implementation plan

1. Add focused unit and shell integration tests for outside-scope symlinks, the two missing Codex disable states, and dangling-symlink uninstallation.
2. Refactor `workflow_hook_config.py` so validation, status, install, and removal share one resolved path and optional scope policy.
3. Add CLI scope flags and a distinct outside-root exit status, then wire the flags and default-no approval into `install.sh` and `uninstall.sh`.
4. Return and display a concrete Codex disable reason from `disabled-status`.
5. Update installation documentation and run the focused suite, full suite, shell syntax checks, skill validation, and diff checks.

## TDD decision

Use TDD. Each issue has a deterministic filesystem or TOML reproduction and the repository already has Python unit tests plus sourced-shell integration tests. Confirm the new tests fail for the reviewed reason before changing production code.

## Parallelization decision

Keep the work sequential. All three fixes change the same helper contract and the install/uninstall call sites that consume it, so parallel edits would overlap and could produce inconsistent safety semantics. No parallel workers will be started.

## Design approval decision

No additional design checkpoint is required. The user explicitly approved fixing the findings, and the scope policy follows the reviewed recommendation: no silent cross-scope mutation, with an explicit default-no override for intentional dotfile symlinks.

## Acceptance criteria

- Project installation does not modify an out-of-project settings target without explicit approval.
- The Python helper independently enforces the allowed root and returns a distinct status for an outside target.
- Codex installation defaults to skip for all three effective user-hook disable states and explains which setting caused it.
- Direct and shell uninstallation reject a dangling settings symlink and preserve the hook file.
- Existing in-scope symlink round trips and all prior tests continue to pass.
