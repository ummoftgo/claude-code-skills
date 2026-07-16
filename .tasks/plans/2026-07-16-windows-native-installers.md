# Windows native installer support

## Goal and non-goals

Add interactive PowerShell 5.1 installers for native Windows Claude Desktop Code and Codex, while keeping the Bash installers for POSIX/WSL. Both platforms must install the same catalogued skills, agents, and workflow hook, track ownership with a v2 manifest, and remove only verified repository-owned content.

Do not package Claude plugins, install third-party tools, launch desktop apps, or add unattended PowerShell flags. `codex-delegate` remains Claude-only.

## Current context

- `install.sh` and `uninstall.sh` contain duplicated component lists and use manifest v1.
- POSIX Codex global skills still target `~/.codex/skills/local`; the supported target is `~/.agents/skills`.
- The Python workflow hook and JSON/TOML merger already preserve unrelated settings and provide rollback-friendly commands.
- Windows needs a PowerShell hook and native paths; project scope does not install hooks.
- The approved user plan fixes the paths, interaction model, migration safety rules, hook JSON shapes, and restart guidance.

## Specification

### Catalog and paths

`components.json` is the single catalog. Every component declares its kind, source, and support for Claude/Codex on POSIX/Windows. All four installers select from it.

- Windows global Claude: `%USERPROFILE%\.claude\skills`, `agents`, `hooks`, `settings.json`.
- Windows global Codex: `%USERPROFILE%\.agents\skills`, `%USERPROFILE%\.codex\agents`, `hooks`, `hooks.json`, `config.toml`.
- Windows project: `.claude\skills`, `.claude\agents`, `.agents\skills`, `.codex\agents`; no project hooks.
- POSIX global Codex skills move to `~/.agents/skills`; project Codex skills move to `.agents/skills`.

Skills default to copy on Windows. Symlinks are offered only when the repository path and destination are on local Windows filesystems. Agents and hooks always copy.

### Manifest and ownership

Manifest v2 is UTF-8 JSON at `<scope>/.claude-code-skills/manifest.json`. It records version plus entries containing platform, scope, client, kind, component, target, method, source, hash, timestamp, and optional configuration before/after state. Writers update atomically and preserve unrelated entries. Readers also import v1 TSV rows as POSIX entries without claiming ownership beyond a matching hash or repository symlink target.

Removal and replacement require an exact v2 entry with an unchanged hash, or a symlink whose resolved target is inside this repository. Missing manifests, changed copies, foreign links/files, and collisions are preserved.

### Migration

On global Codex skill installation, inspect `~/.codex/skills/local/<skill>`. Migrate only catalogued Codex skills proven to be repository-owned by a matching v1/v2 hash or repository symlink target, and only when the new `.agents/skills/<skill>` target is absent. Copy into the new target, record v2 ownership, then remove the legacy item. Preserve modified, unverified, and conflicting entries.

### Windows hook

`hooks/workflow-reminder.ps1` is PowerShell 5.1 compatible and must produce the same JSON output and non-blocking error behavior as the Python hook.

- Claude registration uses an exec hook with `command: powershell.exe` and an `args` array.
- Codex registration uses `command` plus `commandWindows`.
- Existing JSON entries and unrelated TOML are preserved.
- Hook file and configuration changes roll back together on a merge failure.
- If installation changes the effective Codex hook feature from false to true, record before/after state; uninstall restores it only when the effective value still matches the installed after-state.

### UX and diagnostics

PowerShell scripts ask for clients, global/project scope, copy/link for skills when eligible, and global hook installation. They only report detected/missing Node, PHP, Codex CLI, Context7, Chrome, and agent-browser plus suggested commands.

Claude restart guidance is shown only if the installer created the skills or agents directory. Codex hook guidance says to start a new session and approve the hook with `/hooks`.

### Skill and documentation portability

Shared skills use skill names instead of `~/.claude/skills` paths. Bash-only procedures include a platform branch or PowerShell equivalent. `web-browser-preview` uses `127.0.0.1:9333` on native Windows, a dedicated Chrome user-data directory, and reports Chrome/agent-browser readiness without launching or installing them.

## Acceptance criteria

- Catalog contract covers exactly the repository skills, agents, and hook and all installers consume it.
- Windows global/project install, reinstall, and uninstall preserve foreign/modified content and handle copy/link eligibility.
- v1 imports and safe legacy Codex migration behave as specified.
- Claude/Codex JSON merge and Codex TOML state restoration are exact and rollback-safe.
- Python and PowerShell reminder fixtures are behaviorally equivalent when PowerShell is available.
- Existing Python tests and shell syntax checks remain green.
- README/INSTALL document Windows native vs WSL, paths, restart/trust steps, diagnostics, and manual verification.

## Implementation plan

1. Add catalog/manifest contracts and failing tests.
2. Add shared PowerShell installer module plus interactive `install.ps1`/`uninstall.ps1`.
3. Add the PowerShell hook and configuration/TOML merge with transactional rollback.
4. Move Bash target selection to the catalog, adopt manifest v2 compatibility, and add safe legacy migration.
5. Update cross-platform skill procedures and installation documentation.
6. Run focused and full tests, shell/PowerShell syntax checks where available, then request an independent review and address material findings.

## TDD decision

Use test-first development for catalog consistency, v1/v2 ownership, migration decisions, JSON/TOML preservation, rollback, and hook parity because these are deterministic contracts with high destructive-risk value. Use implementation-followed-by-contract-tests for interactive prompts and documentation where isolated red/green cycles are disproportionate.

## Parallelization decision

Keep implementation sequential. The catalog, manifest schema, path resolution, and hook configuration are shared contracts touched by every workstream, so disjoint edit ownership is not stable enough for safe parallel work. Use a separate read-only reviewer after integrated verification.

## Design approval decision

No new checkpoint is required. The user supplied an already-approved implementation plan that fixes the architecture, paths, compatibility, and UX contracts. This artifact restates that design without expanding scope.

## Review remediation (2026-07-17)

### Architecture decision

Keep a hybrid installer architecture. Python remains the platform-neutral catalog/manifest contract layer; Bash owns POSIX filesystem operations and PowerShell owns native Windows paths, links, settings, and rollback. A full Python installer is rejected because Windows native profiles cannot assume Python is installed, bundling it would expand distribution scope, and the Windows-specific failure modes are already expressed and tested in PowerShell 5.1.

### Remediation specification

- POSIX installs and legacy migration stage new content before replacement, preserve foreign regular files, and restore the previous target and manifest on failure.
- Windows TOML inspection tracks multiline basic and literal strings and refuses ambiguous complex values instead of editing string contents.
- Windows ownership selects the POSIX directory hash whenever a manifest entry declares `platform: posix`; directory hashes include empty directories for new Windows entries while retaining compatibility with legacy hashes.
- Windows-supported skills contain executable PowerShell equivalents for state restoration, temporary output, parallel processes, and cross-validation—not prose-only translation instructions.
- Restart and hook-trust guidance is emitted only when the corresponding first-time directory or hook installation actually occurred.
- Contract tests cover every catalog source and supported target, actual local-link lifecycle when available, foreign files, atomic failure rollback, multiline TOML, POSIX v2 migration, and empty-directory modification.
- Removed external installers stay removed; dependency handling is diagnostics-only. Generated cache artifacts are not retained.

### Remediation implementation plan

1. Add focused failing tests for each reproduced ownership, rollback, TOML, hash, and UX state defect.
2. Implement POSIX staging/backup helpers and safe legacy copy cleanup.
3. Implement Windows TOML multiline-state handling, platform-aware hashing, directory-aware ownership, and success-state guidance.
4. Add concrete PowerShell procedures to the Windows-supported skills.
5. Strengthen catalog/link contracts, remove dead external installer code and generated caches, and run the full cross-platform suite.
6. Dispatch three independent read-only reviewers for Windows, POSIX, and contract/documentation verification; address all material disagreement before handoff.

### Remediation TDD and execution decision

Use red-green-refactor for the reproducible defects. Keep implementation sequential because the POSIX installer, Windows common module, catalog contract, and shared tests overlap. Parallelism is reserved for the final read-only reviews explicitly requested by the user.
