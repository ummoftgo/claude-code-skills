# Codex Hook Activation During Install

## Goal and non-goals

When Codex hooks are disabled in an effective personal `config.toml`, ask whether to enable them and install a working workflow hook. Do not silently install a hook that cannot run. Do not modify inline hook definitions, invalid TOML, untrusted-project state, or enterprise-managed `requirements.toml` policies.

## Specification

1. On an effective `[features] hooks = false` or deprecated `codex_hooks = false`, explain the reason and ask with default `No` whether to activate hooks and continue installation.
2. For global installation, update the user config. For project installation that inherits a disabled user value, write `hooks = true` to the project config so the global preference remains unchanged.
3. Normalize a directly disabled deprecated key to the canonical `hooks = true` form. Preserve unrelated TOML content, comments, file mode, and a valid settings symlink.
4. Validate and activate before copying the hook file. If activation cannot be performed safely, stop without partially installing the hook.
5. Apply the existing install-root check to the config path. An intentional outside dotfiles target still requires the existing default-no scope approval.
6. If the user declines activation, preserve the config and skip hook installation.

## TDD decision

Use TDD. Add focused helper tests for canonical, deprecated, inherited-project, symlink, and invalid-TOML behavior plus shell integration tests for accepting and declining activation.

## Parallelization decision

Keep the work sequential because the helper CLI, installer prompt flow, and shared tests change one contract. No workers are needed.

## Design approval decision

The user explicitly approved this configuration-changing behavior after reviewing the proposed global/project scope and exclusions.

## Acceptance criteria

- Accepting the prompt produces an enabled config and a configured hook.
- Project activation overrides the user value without modifying the user file.
- Declining leaves both config and hook installation unchanged.
- Invalid TOML and unsafe paths stop before hook files are copied.
- Existing installation, removal, reminder, and skill tests continue to pass.
