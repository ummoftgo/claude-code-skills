# Personal Workflow Hook Hardening

## Goal and non-goals

Fix the independently reviewed workflow-hook gaps that are realistic for a personal Claude Code/Codex setup. Preserve safe dotfiles symlinks through explicit approval. Do not build enterprise policy discovery, a general-purpose path-security framework, or exhaustive TOML compatibility.

## Specification

1. Before install or removal touches the hook script, resolve the final hook path against `INSTALL_BASE_DIR`. Allow an intentional outside target only after a default-no confirmation; reject dangling links safely.
2. For project Codex installs, compute the effective hooks feature from the user config and the higher-precedence project config. A project value overrides the user value; an absent project value inherits it.
3. Treat `allow_managed_hooks_only` as a managed `requirements.toml` policy, not a `config.toml` option. This personal installer will not attempt to discover enterprise-managed requirements.
4. Make the reminder hook return success for valid non-object JSON input.
5. Make the Python 3.10 fallback recognize the common dotted forms `features.hooks` and `features.codex_hooks`.

## TDD decision

Use focused TDD because every change has a deterministic regression case in the existing unit and sourced-shell test harness. Confirm the new tests fail for the reviewed reasons before implementation.

## Parallelization decision

Keep implementation sequential because the helper CLI contract, installer, uninstaller, and integration tests overlap. The requested independent sub-agent review happens only after implementation and does not edit files.

## Design approval decision

The user approved the reviewed fixes and explicitly requested proportional handling for personal use. No additional design checkpoint is needed.

## Acceptance criteria

- An outside hook-script target is not written or deleted without explicit approval.
- A project with no feature override inherits the user-level Codex hooks setting; an explicit project setting wins.
- `allow_managed_hooks_only` in `config.toml` is not reported as effective.
- Array, string, and null hook inputs exit successfully without output.
- Python 3.10 fallback recognizes the two common dotted feature keys.
- Existing tests, shell syntax, skill validation, and diff checks pass.
