# Resumable handoff template

Preserve an established repository format when it already contains the same fields. Otherwise use this compact structure.

```markdown
# Handoff: <task>

Updated: YYYY-MM-DD HH:MM <timezone>

## Checkpoint

- Branch: `<branch>`
- Commit: `<full-or-short-hash>` or `pending (this handoff is included in the checkpoint commit)`
- Upstream: `<remote/branch and synchronization state>`
- Scope committed: `<paths or concise boundary>`

## Completed

- <observable completed outcome>

## Remaining

- <next bounded task and any dependency>

## Verification

- `<exact command>` — PASS/FAIL: <important result>

## Resume

1. `<exact command or file entry point>`
2. <next action and expected state>

## Intentionally dirty or generated paths

- `<path>` — <why it remains and whether to preserve or regenerate>

## Known failures or risks

- <failure evidence, limitation, or `None known`>
```

Record artifact hashes only when they are needed to distinguish generated outputs or reproduce a result. Never copy secrets into the handoff.
