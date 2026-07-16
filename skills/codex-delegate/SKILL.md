---
name: codex-delegate
description: "Delegate code review or implementation tasks to Codex. Trigger when user says '코덱스에게 검토해', '코덱스에게 구현시켜', 'codex로 리뷰해', 'codex로 만들어줘' or similar. Prefer OpenAI's official Claude Code plugin (openai/codex-plugin-cc) slash commands when installed; otherwise fall back to the codex CLI. For review: spawns 4 parallel sub-agents (2 code quality + 2 security). For implementation: splits work by frontend/backend or screen/function into parallel sub-agents. Always creates a context MD file in .agent-works/ to pass project context to Codex sessions that have no prior knowledge."
---

# Codex Delegate

Delegate code review or implementation to Codex CLI sub-agents. Because each Codex session starts fresh with no conversation history, always prepare a context file first.

## Step -1: Choose How to Call Codex (Plugin vs CLI)

Before anything else, decide how Codex will be invoked. If OpenAI's official Claude Code plugin [openai/codex-plugin-cc](https://github.com/openai/codex-plugin-cc) is installed, drive Codex through the plugin's slash commands. Otherwise, fall back to the raw `codex` CLI described under [Codex CLI Invocation](#codex-cli-invocation).

Detect the plugin (marketplace `openai-codex`, plugin `codex`):

Choose the detection command for the active platform. Do not require Git Bash on native Windows.

```bash
# Prints "plugin" if the official Codex plugin is installed, otherwise "cli".
# Cheap filesystem check (a few stats) — NOT a readiness probe. Do NOT run
# `setup --json` here just to detect the plugin; that spins up node + the codex
# app-server and is the real source of latency (see note below).
PLUGIN_BASE="$HOME/.claude/plugins/cache/openai-codex/codex"
PLUGIN_ROOT="$(ls -d "$PLUGIN_BASE"/*/ 2>/dev/null | sort -V | tail -1)"
COMPANION="${PLUGIN_ROOT%/}/scripts/codex-companion.mjs"
if [ -n "$PLUGIN_ROOT" ] && [ -f "$COMPANION" ]; then
  echo plugin
else
  echo cli
fi
```

```powershell
# Native Windows PowerShell equivalent.
$pluginBase = Join-Path $env:USERPROFILE '.claude\plugins\cache\openai-codex\codex'
$pluginRoot = Get-ChildItem -LiteralPath $pluginBase -Directory -ErrorAction SilentlyContinue |
  Sort-Object @{ Expression = {
    $numericPrefix = [regex]::Match($_.Name, '^\d+(?:\.\d+){1,3}').Value
    if ($numericPrefix) { [version]$numericPrefix } else { [version]'0.0' }
  } }, Name | Select-Object -Last 1
$companion = if ($pluginRoot) { Join-Path $pluginRoot.FullName 'scripts\codex-companion.mjs' } else { $null }
if ($companion -and (Test-Path -LiteralPath $companion -PathType Leaf)) { 'plugin' } else { 'cli' }
```

All `node` and `codex` foreground invocations below work in PowerShell too. Bash-only subshells, traps, `$!`, background `&`, and `/tmp` paths must be replaced with PowerShell `try/finally`, `Start-Job` or `Start-Process`, and files under `$env:TEMP`. Preserve the same read-only/write sandbox flags and restoration guarantees.

**Fallback policy** — only the *absence* of the plugin sends you to the CLI path:

- Route to **cli** only when `PLUGIN_ROOT` is empty or `$COMPANION` does not exist (`[ ! -f "$COMPANION" ]`). That is the one fast, unambiguous "plugin not installed" signal — do not pattern-match on a `MODULE_NOT_FOUND` string, which depends on the Node loader's output format.
- Once you have committed to the **plugin** path, treat any failure of `node "$COMPANION" ...` as a **real Codex execution failure** (auth expired, `codex` binary missing, app-server failure, sandbox refusal, or genuine review findings) and report it. Do **not** silently retry on the CLI — the CLI shares the same `codex` binary and auth, so it would just fail the same way (or worse, double-run the work).

- **plugin** → use the slash commands. They wrap the Codex app server using the same local `codex` binary, auth, and config.
  - Review → `/codex:review` (read-only), or `/codex:adversarial-review` for a steerable design challenge. Both accept `--base <ref>`, `--wait`, `--background`.
  - Implement / fix / investigate → `/codex:rescue <task>` (write-capable; add `--background`, `--wait`, `--resume`, `--fresh`, `--model`, `--effort` as needed).
  - Manage jobs → `/codex:status`, `/codex:result`, `/codex:cancel`.
  - You still create the `.agent-works/` context file (Step 0) and reference it in the slash-command prompt so Codex reads it at session start.
- **cli** → use `codex -a never exec ...` exactly as documented below.

> **Do not pre-run a readiness check.** `setup --json` (or `/codex:setup`) probes node, npm, `codex --version`, `codex app-server`, and auth — a multi-second round-trip — so reserve it for *diagnosis after a failure*, not as a gate before every call. The cheap filesystem check above is the only thing you need to choose a path; go straight to `review`/`task` and let the first real call surface any readiness problem (its error message is already actionable).

### Plugin Invocation Recipe

The slash commands are the preferred entry point, but inside an agent/subagent context they may not be directly invocable. In that case call the bundled **companion script** directly — it is exactly what the slash commands wrap (same `codex` binary, auth, and config), so you never need to read `commands/*.md` to discover the call:

```bash
# Resolve the installed plugin root (highest installed version dir)
PLUGIN_ROOT="$(ls -d "$HOME/.claude/plugins/cache/openai-codex/codex"/*/ 2>/dev/null | sort -V | tail -1)"
COMPANION="${PLUGIN_ROOT%/}/scripts/codex-companion.mjs"

node "$COMPANION" setup --json                          # diagnose readiness AFTER a failure — not a pre-gate
node "$COMPANION" review --wait --base <ref>            # read-only native review of local git state (always foreground)
node "$COMPANION" adversarial-review --wait --base <ref> "focus text"   # steerable review (always foreground)
node "$COMPANION" task --write "<task>"                 # implement/fix — omit --write to stay read-only (slash: /codex:rescue)
node "$COMPANION" task --background --write "<task>"    # same, but as a real background job
node "$COMPANION" result                                # collect a backgrounded `task --background` job's output
```

Companion subcommand = slash-command name. Argument map:

| Subcommand | Purpose | Key args |
|---|---|---|
| `review` | Read-only native review of **local git state** | `--base <ref>`, `--scope auto\|working-tree\|branch`. **Always foreground** — `--wait` is the effective default; a passed `--background` is parsed but ignored |
| `adversarial-review` | Review with custom focus / design challenge | same as `review`, plus trailing `focus text` |
| `task` (slash `/codex:rescue`) | Implement / fix / investigate — **read-only unless `--write`** | `--write` (enables `workspace-write`), `--background` (real background job → collect with `result`), `--resume`, `--fresh`, `--model`, `--effort` |
| `status` / `result` / `cancel` | Inspect or stop background jobs | — |

**Foreground vs background**: the companion `review` / `adversarial-review` subcommands **always run foreground** — a passed `--background` is silently ignored, so don't expect a collectable job from them. For a long review, background the `node` call itself with Claude's `run_in_background` instead. Only `task --background` enqueues a real background job you later collect with `result`. (The slash commands' `--background` is a separate runner-side flag handled by Claude, not the companion.) Note also that companion `task` defaults to **read-only** — pass `--write` for any implement/fix that must edit files. `review` is read-only and **rejects custom focus text** — use `adversarial-review` when you need to steer the review.

## Step 0: Create Context File

Before dispatching any Codex agent, create a context MD file in the project's `.agent-works/` directory.

**Filename rule**: `YYYYMMDD-HHMMSS-{type}-{slug}.md` — timestamp + type + content description.
Use unique names to avoid conflicts when multiple tasks run concurrently or files are locked.

```
.agent-works/
  20260319-143022-review-user-login.md
  20260319-143055-implement-file-upload-api.md
  20260319-143055-implement-file-upload-frontend.md  ← parallel agents get separate files
```

**Context file template**:

```markdown
# Task: [review|implement] — [feature name]
**Date**: [YYYY-MM-DD HH:MM]
**Type**: [review / implement]

## Project Overview
[Project description and tech stack: PHP + JS/Svelte/HTMX/jQuery, DB type, auth approach]

## Current State
[Summary of work done so far; list of recently changed files]

## Task Description
[Specific task for Codex: what to review OR what to implement]

## Relevant Files
[List of file paths that are in scope — be explicit]

## Constraints
[Coding conventions, files NOT to touch, naming rules, etc.]

## Tech Stack Details
- Backend: PHP (PDO, sessions, file uploads, ...)
- Frontend: [vanilla JS / jQuery / Svelte / HTMX — whichever applies]
- DB: [MySQL / MariaDB / ...]
- API response format: {"success": bool, "data": ..., "error": "..."}
```

Create one file per agent when dispatching parallel sub-agents.

---

## Mode 1: Review

**If the plugin is installed**, prefer `/codex:review` (or the `review` companion subcommand) for a standard read-only review of the current changes, or `/codex:adversarial-review` when the user wants the design and tradeoffs pressure-tested. Use `--base <ref>` for branch review and `--background` for multi-file changes, then collect output with `/codex:status` and `/codex:result`. This replaces the parallel CLI sub-agent fan-out below.

> **Reviewing one specific commit (not the working tree).** `review` always diffs against **HEAD** using a three-dot (`base...HEAD`, merge-base) range, so it **cannot isolate a single mid-history commit** while HEAD is ahead of it. To review exactly commit `<sha>` and nothing else, detach onto it so it becomes HEAD, diff against its parent, then restore:
>
> ```bash
> git status --short --untracked-files=all          # confirm clean tree (untracked is OK)
> (                                                   # subshell so the trap fires on exit
>   set -e
>   # current ref: branch name, or the commit SHA if HEAD is already detached
>   orig_ref="$(git symbolic-ref --quiet --short HEAD || git rev-parse --verify HEAD)"
>   trap 'git checkout --quiet "$orig_ref"' EXIT      # ALWAYS restore — success, failure, or abort
>   git checkout --detach <sha>                        # <sha> is now HEAD
>   node "$COMPANION" review --wait --base <sha>^      # base...HEAD == only <sha>
> )                                                    # trap restores orig_ref here
> ```
>
> Native Windows PowerShell equivalent (foreground only, with unconditional HEAD restoration):
>
> ```powershell
> git status --short --untracked-files=all
> $originalRef = (git symbolic-ref --quiet --short HEAD 2>$null)
> if (-not $originalRef) { $originalRef = (git rev-parse --verify HEAD).Trim() }
> try {
>   git checkout --detach <sha>
>   if ($LASTEXITCODE -ne 0) { throw 'Could not detach onto the requested commit.' }
>   node $companion review --wait --base '<sha>^'
>   if ($LASTEXITCODE -ne 0) { throw 'Codex review failed.' }
> } finally {
>   git checkout --quiet $originalRef
> }
> ```
>
> Two reasons this must run with `--wait` (foreground): (1) the trap restores `HEAD` only *after* the review returns, and (2) the companion `review` runs foreground regardless of any `--background` flag (see the recipe note above) — so there is no safe way to background it here. Capturing `orig_ref` via `symbolic-ref || rev-parse HEAD` also keeps the restore correct even if you started from an already-detached HEAD (where `git branch --show-current` would be empty).

**If only the CLI is available**, dispatch 4 Codex CLI sub-agents in parallel — 2 for code quality, 2 for security.

| Agent | Focus | Codex prompt |
|---|---|---|
| Quality-1 | Readability, structure, duplication | `"코드 품질 검토 (가독성·구조·중복): .agent-works/[file] 참조"` |
| Quality-2 | Performance, maintainability | `"코드 품질 검토 (성능·유지보수성): .agent-works/[file] 참조"` |
| Security-1 | PHP backend security | `"PHP 백엔드 보안 검토 (SQL injection·CSRF·세션·파일업로드): .agent-works/[file] 참조"` |
| Security-2 | Frontend JS/DOM security | `"프론트엔드 보안 검토 (XSS·DOM·토큰 노출): .agent-works/[file] 참조"` |

After all agents return, aggregate findings into a single review summary for the user. Group by severity: Critical → High → Medium → Low. Write the summary in the same language the user used when requesting the review.

---

## Mode 2: Implement

**If the plugin is installed**, hand the work to Codex with `/codex:rescue <task>` (write-capable by default). Add `--background` for long tasks and `--resume`/`--fresh` to control thread continuity, then check in with `/codex:status` and `/codex:result`. Reference the `.agent-works/` context file in the task text. For multi-part splits, you can run separate `/codex:rescue` handoffs per scope.

**If only the CLI is available**, dispatch implementation sub-agents with `codex -a never exec -s workspace-write ...` as shown under [Codex CLI Invocation](#codex-cli-invocation).

Before dispatching implementation agents: if the `use-context7` skill is installed, invoke it by name (`use-context7`) to query the relevant library/framework docs for each layer being implemented. Do this before writing agent prompts — the queried docs should inform the prompt's requirements and constraints.

Analyze the task scope and choose a split strategy:

| Split | When | Agents |
|---|---|---|
| Backend + Frontend | API spec confirmed, both sides independent | 2 agents |
| Layout + Logic | Single page, UI markup and JS are separable | 2 agents |
| Single | Simple task or cannot be split cleanly | 1 agent |

Each agent receives:
- Its own context file (separate file per agent)
- Explicit scope: which files to create/edit
- Hard constraint: "Do NOT touch files outside your scope"

After agents return:
1. **Conflict check**: Confirm no two agents modified the same file.
2. **Naming consistency**: Verify API endpoint names, DB column names, and variable names align across backend and frontend.
3. **Integration test**: Run the application and test the happy path end-to-end.
4. **Context file cleanup**: Delete or archive the `.agent-works/` files for this task. (Adding `.agent-works/` to `.gitignore` is recommended.)

---

## Codex CLI Invocation

Use this section only when the official Codex plugin is **not** installed (see [Step -1](#step--1-choose-how-to-call-codex-plugin-vs-cli)).

```bash
# Non-interactive, read-only sandbox — for review / analysis tasks
# -a (--ask-for-approval) must come BEFORE the exec subcommand
codex -a never exec -s read-only "task description. Context: .agent-works/FILENAME.md"

# Non-interactive, workspace-write sandbox — for implementation tasks
codex -a never exec -s workspace-write "task description. Context: .agent-works/FILENAME.md"

# Capture last message to file (useful for parallel background execution)
codex -a never exec -s read-only -o /tmp/out.txt "task description. Context: .agent-works/FILENAME.md"

# Interactive — when you want to inspect output step by step
codex "task description. Context: .agent-works/FILENAME.md"
```

**Parallel execution pattern** — run agents in background and wait for all to finish:
```bash
codex -a never exec -s read-only "task 1. Context: .agent-works/FILE1.md" > /tmp/r1.txt 2>&1 &
PID1=$!
codex -a never exec -s read-only "task 2. Context: .agent-works/FILE2.md" > /tmp/r2.txt 2>&1 &
PID2=$!

# Wait for all background jobs to complete (preferred over polling)
wait $PID1 $PID2
```

Native Windows PowerShell 5.1 equivalent — keep context and result files under `$env:TEMP`, start every reviewer before waiting, and always clean up temporary files:

```powershell
$runDirectory = Join-Path $env:TEMP ('codex-delegate-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $runDirectory | Out-Null
$processes = @()
try {
  $tasks = @(
    @{ Name = 'quality'; Prompt = '코드 품질 검토. Context: .agent-works/QUALITY.md' },
    @{ Name = 'security'; Prompt = '보안 검토. Context: .agent-works/SECURITY.md' }
  )
  foreach ($task in $tasks) {
    $result = Join-Path $runDirectory ($task.Name + '.txt')
    $stderr = Join-Path $runDirectory ($task.Name + '.stderr.txt')
    $arguments = @('-a', 'never', 'exec', '-s', 'read-only', '-o', ('"' + $result + '"'), ('"' + $task.Prompt + '"')) -join ' '
    $processes += Start-Process -FilePath 'codex' -ArgumentList $arguments -PassThru -RedirectStandardError $stderr
  }
  $processes | Wait-Process
  foreach ($process in $processes) {
    if ($process.ExitCode -ne 0) { Write-Warning "Codex reviewer failed with exit code $($process.ExitCode)." }
  }
  Get-ChildItem -LiteralPath $runDirectory -Filter '*.txt' -File | Get-Content
} finally {
  Remove-Item -LiteralPath $runDirectory -Recurse -Force -ErrorAction SilentlyContinue
}
```

> **Key rules**:
> - `-a never` is a top-level flag — place it **before** `exec`, not after
> - Use `-s read-only` for review tasks; `-s workspace-write` for tasks that write files
> - Do **not** use `--dangerously-bypass-approvals-and-sandbox` — it disables all sandboxing

Pass the context filename explicitly in the prompt so Codex reads it at the start of its session.
