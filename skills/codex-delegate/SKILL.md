---
name: codex-delegate
description: "Delegate code review or implementation to Codex. Trigger when user says '코덱스에게 검토해', '코덱스에게 구현시켜', 'codex로 리뷰해', 'codex로 만들어줘' or similar. Reviews go through Codex's native reviewer (`codex exec review` with `--commit`, `--base`, or `--uncommitted`) and are collected from a result file; implementation goes through `codex -a never exec -s workspace-write` once the user has approved it. Reviews stay read-only — they never change git state and never write a context file under any circumstance; context files belong only to implementation prompts that are too large to pass inline. When OpenAI's official codex-plugin-cc is installed, its `/codex:*` slash commands are an equivalent entry point."
---

# Codex Delegate

A thin bridge to the local `codex` CLI. A Codex session starts with no conversation
history, so every call must carry its own scope in the prompt.

Two rules apply to every invocation:

- `-a never` is a **top-level** flag: it goes **before** the `exec` subcommand
  (`codex -a never exec ...`), never after it.
- Never pass `--dangerously-bypass-approvals-and-sandbox` — it disables sandboxing.

## Mode 1: Review (read-only)

Use Codex's native reviewer. It resolves the diff from git itself, so **never
checkout, detach, or stash anything to shape the range** — a read-only review must
not touch the user's working tree.

```bash
codex -a never -s read-only exec review --commit <SHA>    # exactly one commit
codex -a never -s read-only exec review --base main       # current branch vs. a base
codex -a never -s read-only exec review --uncommitted     # staged + unstaged + untracked
```

Pick exactly one of `--commit` / `--base` / `--uncommitted`. Also available:
`--title <TITLE>`, `-m <MODEL>`, and `--output-schema <FILE>` / `--json` for
machine-readable output.

**A range flag and a custom focus are mutually exclusive.** All three of `--commit`,
`--base`, and `--uncommitted` conflict with the trailing `[PROMPT]` argument (and
therefore with `-`, which is just `[PROMPT]` read from stdin) — verified against
codex-cli 0.145.0, which rejects the combination at argument parsing:

```
error: the argument '--uncommitted' cannot be used with '[PROMPT]'
```

The `[PROMPT]` in `codex exec review --help`'s usage line is real but only valid
without a range flag, so do not infer that the two compose. Choose per need:

```bash
# Native range resolution, reviewer's own default focus:
codex -a never -s read-only exec review --commit <SHA>

# Custom focus, no range flag — the reviewer resolves its own default range:
codex -a never -s read-only exec review "보안 위주로 검토: SQL injection, CSRF, 세션, 파일 업로드"
printf '%s' "$focus_text" | codex -a never -s read-only exec review -
```

When you genuinely need **both** an exact range and a custom focus, do not fight the
reviewer: use a plain read-only `exec` and state the range in the prompt, so Codex
resolves the diff itself with git.

```bash
codex -a never -s read-only exec "Review only the changes introduced by commit <SHA> (diff it against its parent). Focus on SQL injection, CSRF, session handling, and file uploads. Report findings only — change nothing."
```

### Collecting the result

`codex exec` prints progress to **stderr** and only the final answer to **stdout**.
So redirecting stdout is all it takes to collect the result — **use stdout, not
`-o`**, because one channel means one copy of the answer and no way to double-report
it.

`-o` / `--output-last-message <FILE>` is *additive*, not a redirect: it writes the
final message to FILE **while still printing it to stdout**. Verified against
codex-cli 0.145.0 — after `codex ... -o out.txt > stdout.txt`, both files hold the
answer (the `-o` copy has no trailing newline). Treating `-o` as "send the answer to
a file instead of stdout" is what produces duplicated findings: passing stdout
through *and* reading the result file reports the review twice and breaks any
parsing or aggregation downstream. If you do use `-o`, pick exactly one reader —
either discard stdout (`> /dev/null`) and read the file, or read stdout and ignore
the file.

Create the run directory outside the user's repository and remove it whether the
review succeeds or fails. **Check that `mktemp` actually succeeded before doing
anything else** — an empty `$outdir` turns `> "$outdir/review.md"` into a write to
**`/review.md`**, which fails as a confusing permission error unprivileged and
truncates a root-level file privileged, and it leaves the trap holding
`rm -rf ""` — one dropped quote away from `rm -rf /`. Validate first, arm the trap
second, run Codex third:

```bash
sha="<SHA>"                                                   # the commit to review
outdir="$(mktemp -d "${TMPDIR:-/tmp}/codex-review-XXXXXX")" || outdir=''
if [ -z "$outdir" ] || [ ! -d "$outdir" ]; then               # never proceed on a bad path
  printf 'codex review aborted: could not create a run directory under %s\n' \
    "${TMPDIR:-/tmp}" >&2
  exit 1
fi
trap 'rm -rf "$outdir"' EXIT                                  # armed only once $outdir is valid

if codex -a never -s read-only exec review --commit "$sha" \
     > "$outdir/review.md" 2> "$outdir/review.err.txt"; then   # stdout = findings only
  cat "$outdir/review.md"                                     # findings
else
  status=$?
  printf 'codex review failed (exit %d):\n' "$status" >&2
  cat "$outdir/review.err.txt" >&2                            # the actual cause
  exit "$status"
fi
```

If you only want to *see* the review, drop the redirection entirely and let stdout
reach the terminal — the file is worth creating only when something else has to read
the findings afterwards.

Do **not** use `2>&1` or fold stderr into the result file: the progress stream
carries the session banner, hook lines, and token counts, and it also renders the
final message itself, so merging the two contaminates the review text *and*
duplicates the answer. Read `review.md` for findings; read `review.err.txt` only
when the exit code is non-zero, to explain the failure. Never read the result file
without checking the exit code first — on failure it may be empty or missing, and
the cleanup step will take the stderr file with it.

PowerShell uses the same `codex` flags verbatim; only the shell plumbing differs.
Keep result files under `$env:TEMP` and delete them in a `finally` block. Prefer
`Start-Process` with `-RedirectStandardOutput` / `-RedirectStandardError` over `>`
and `2>` there: in PowerShell 5.1 a native command's stderr can surface as
`ErrorRecord`s and trip `$ErrorActionPreference = 'Stop'`, even on a successful
review. `-RedirectStandardOutput` gives the same single-copy result as the POSIX
example, so `-o` is unnecessary here too. Wait with `-Wait -PassThru`, not with
`Wait-Process` on a `-PassThru` object: in 5.1 the `ExitCode` of an object that was
not waited on directly can come back `$null`.

Three Windows-specific traps in that block:

- **Always read result files with `-Encoding UTF8`.** Codex writes UTF-8 without a
  BOM, but `Get-Content` in PowerShell 5.1 defaults to the ANSI code page, so a
  review containing non-ASCII text (Korean findings, for instance) comes back
  mojibake. PowerShell 7+ defaults to UTF-8, so the flag is redundant there and
  harmless — spell it out for 5.1.
- **Create and verify the run directory *before* the `try`.** `finally` must never
  run `Remove-Item` on a path that was never created, or on `$null` if `$env:TEMP`
  is unset and `Join-Path` fails. Validate up front and let the whole review abort
  if the directory is not there.
- **Send the failure diagnosis to stderr and exit non-zero.** `Write-Warning`
  followed by a bare `Get-Content` of the error file is the trap this block used to
  fall into, and it fails three ways at once: `$WarningPreference` can silence the
  warning, the error text lands on **stdout** right next to real findings, and the
  script keeps running and still exits `0` — so the caller records a *successful*
  review whose "findings" are a Codex crash dump. Write diagnostics with
  `[Console]::Error.WriteLine(...)`, which goes to the process's stderr regardless of
  `$ErrorActionPreference` / `$WarningPreference` and without the `Write-Error`
  banner and `+ CategoryInfo` decoration wrapped around the cause, and end the run
  with `exit`.

```powershell
$sha = '<SHA>'
if ([string]::IsNullOrWhiteSpace($env:TEMP)) {
  throw 'codex review aborted: $env:TEMP is not set, so no run directory can be created.'
}
$runDirectory = Join-Path $env:TEMP ('codex-review-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $runDirectory -ErrorAction Stop | Out-Null
if (-not (Test-Path -LiteralPath $runDirectory -PathType Container)) {   # nothing to clean up yet
  throw "codex review aborted: could not create the run directory $runDirectory."
}
$resultFile = Join-Path $runDirectory 'review.md'
$errorFile = Join-Path $runDirectory 'review.err.txt'
$exitCode = 1                                           # fail closed until Codex reports success
try {                                                   # entered only with a real directory
  $arguments = @('-a', 'never', '-s', 'read-only', 'exec', 'review', '--commit', $sha)
  $process = Start-Process -FilePath 'codex' -ArgumentList ($arguments -join ' ') `
    -RedirectStandardOutput $resultFile -RedirectStandardError $errorFile `
    -Wait -PassThru
  if ($null -ne $process.ExitCode) { $exitCode = $process.ExitCode }  # $null stays a failure
  if ($exitCode -eq 0) {
    Get-Content -LiteralPath $resultFile -Encoding UTF8          # findings -> stdout, 5.1 is ANSI
  } else {
    [Console]::Error.WriteLine(('codex review failed (exit {0}):' -f $exitCode))
    if (Test-Path -LiteralPath $errorFile) {
      $cause = Get-Content -LiteralPath $errorFile -Raw -Encoding UTF8    # same encoding trap
      if ($cause) { [Console]::Error.WriteLine($cause) }         # cause -> stderr, never stdout
    }
  }
} finally {
  Remove-Item -LiteralPath $runDirectory -Recurse -Force -ErrorAction SilentlyContinue
}
if ($exitCode -ne 0) {
  exit $exitCode                                        # cleanup already ran; caller sees failure
}
```

Both blocks now carry the same contract: **findings on stdout, diagnosis on stderr,
non-zero exit on failure, run directory removed either way.**

**Why `exit $exitCode` after the `finally`, and not a bare `throw`.** A `throw` is a
script-terminating error, and Windows PowerShell flattens that to a fixed process
exit code: with `powershell.exe -File`, "when a script-terminating error occurs, the
exit code is set to `1`", and `-Command` behaves the same, with the documented remedy
being "add `exit $LASTEXITCODE` to your command string or script block"
([about_PowerShell_exe](https://learn.microsoft.com/powershell/module/microsoft.powershell.core/about/about_powershell_exe?view=powershell-5.1)).
So `throw` would report *a* failure but throw away Codex's own exit code — and worse,
`$ErrorActionPreference` "can suppress `throw` when set to `SilentlyContinue` or
`Ignore`", in which case "the error doesn't propagate and execution continues at the
next statement"
([about_Error_Handling](https://learn.microsoft.com/powershell/module/microsoft.powershell.core/about/about_error_handling?view=powershell-5.1)),
which is exactly the run-on-after-failure bug this block exists to prevent. `exit` is
not suppressible and sets the process exit code verbatim. Putting it *after* the
`try`/`finally` keeps the cleanup provable: the `finally` statements "run regardless
of whether the `try` block encounters a terminating error", and the only `exit` case
the docs spell out is one issued "from within a `catch` block"
([about_Try_Catch_Finally](https://learn.microsoft.com/powershell/module/microsoft.powershell.core/about/about_try_catch_finally?view=powershell-5.1)),
so nothing here rests on `exit`-inside-`try` semantics — the run directory is already
gone before `exit` runs. Use this shape as a script; if you paste it into a function
or dot-source it, replace the final `exit` with `throw` and let the caller map the
failure to an exit code — the diagnosis goes to stderr either way.

Report the findings grouped by severity (Critical → High → Medium → Low), in the
language the user used to ask. A review never edits code — findings only.

## Mode 2: Implement (write-capable)

Only after the user has approved the change:

```bash
codex -a never exec -s workspace-write "<task, explicit file scope, constraints>"
```

State the in-scope files explicitly and add a hard "do not touch files outside this
scope" constraint. If the work splits cleanly (e.g. backend vs. frontend), use one
call per independent scope and make sure no two scopes list the same file. If the
`use-context7` skill is installed, invoke it by name for the relevant
libraries/frameworks *before* writing the prompt. Afterwards check for overlapping
edits, cross-layer naming, and the happy path — split strategy, verification steps,
and a context-file template are in
[references/implementation-handoff.md](references/implementation-handoff.md).

## Passing context

Prefer the prompt argument; pipe long text in via stdin (`-`). Write a context file
**only** when the context is too large for a prompt or must be reused across calls:
put it in the project's `.agent-works/` directory (recommended in `.gitignore`) or
under `$TMPDIR` / `$env:TEMP`, reference its path in the prompt, and delete it when
the task finishes — whoever creates the file removes it. Never create a context file
for a review, and never create one "just in case".

## Optional: official Codex plugin

If OpenAI's [codex-plugin-cc](https://github.com/openai/codex-plugin-cc) is
installed, `/codex:review`, `/codex:adversarial-review`, `/codex:rescue`,
`/codex:status`, `/codex:result`, and `/codex:cancel` are equivalent entry points —
they wrap the same local `codex` binary, auth, and config. Use them when the current
context can invoke slash commands; otherwise use the CLI above. The plugin's flag
surface is another project's contract, so confirm it against its README rather than
assuming; as documented there:

- `/codex:review` is read-only and **not** steerable — it takes no custom focus text.
  Use `/codex:adversarial-review` when the review needs to be steered.
- `/codex:review`, `/codex:adversarial-review`, and `/codex:rescue` all accept
  `--wait` and `--background`. A backgrounded job is a real job: track it with
  `/codex:status`, collect it with `/codex:result`, stop it with `/codex:cancel`.

When a `/codex:*` command fails:

- Report the failure instead of silently re-running the work elsewhere. **If a job ID
  already exists, never repeat that work on the CLI** — the job can end up running
  twice. If the failure happened *before* a job was created (the Node wrapper or
  `codex app-server` never produced an ID), the CLI is a genuinely separate path and
  switching to it is safe.
- Do not pre-flight `/codex:setup` as a gate before delegating: it probes node, npm,
  `codex --version`, `codex app-server`, and auth, which is a multi-second round-trip,
  and the first real call already reports readiness problems. Run it *after* a failure,
  as diagnosis.
- Do not call the plugin's internal scripts or probe its cache directories — the cache
  layout, script names, and argument surfaces are private and change without notice.
