---
name: branch-merge-review
description: "Run a first-time (initial) discovery review of all committed changes between the current branch and main/master before merging. Trigger when user says '브랜치 리뷰해줘', '머지 전에 리뷰해줘', 'PR 리뷰해줘', 'branch review', 'merge review', or similar. Reviewers never modify code, so a read-only branch review ('수정하지 말고 브랜치 리뷰해줘') still belongs here. Work mode outranks scope, so do NOT use this skill for a recheck of prior findings, a second or final review, a final approval or sign-off decision, or evidence-first verification of specific claims or raw data — use evidence-first-review instead, even when the scope is a PR, branch, or merge diff ('이 PR의 이전 지적을 재검토하고 최종 승인해줘'). Collection is commit-based, so this skill cannot review uncommitted staged, unstaged, or untracked work. Not for a single file or feature outside a branch diff (use code-quality-review or web-security-review)."
---

# Branch Merge Review

Review all committed diff changes against main/master with a parallel reviewer team: **one quality reviewer per detected backend language**, one frontend quality reviewer when a browser surface exists, and one security reviewer — each invoking the appropriate installed skill (`code-quality-review` or `web-security-review`). The team leader waits for every reviewer to finish (Step 3), cross-validates Critical/High findings with grep audit patterns (Step 4), and produces a consolidated report. Reviewers NEVER modify code — findings only.

## Platform command selection

Invoke installed skills by name (`code-quality-review`, `web-security-review`); never open them through a hard-coded `~/.claude/skills` path. Git commands work in Bash and PowerShell. For searches, prefer cross-platform `rg`; when it is unavailable use `grep` on POSIX or `Get-ChildItem -Recurse | Select-String` on Windows PowerShell. Translate the Bash collection block in Step 1 to PowerShell arrays and `ForEach-Object` when the active shell is PowerShell instead of requiring Git Bash.

> **Read-only mode (priority rule).** Reviewers never modify code regardless. Additionally, if the user asked to review **without writing anything** ("수정하지 말고", "read-only", or a read-only sandbox), the team leader must not write to the workspace at all: no tool installs, no worktree or Git state changes, and no file of any kind — report files included. Inline output is the default anyway (Step 5); under this constraint it is the only option even if the user asks for a file, so say that a report file needs write permission. Tell each spawned reviewer to run read-only as well.
>
> This skill is the right choice for a read-only PR/branch review: a "수정하지 말고" constraint does not move a branch- or PR-scoped review to `evidence-first-review` — run *this* skill read-only instead.

## Routing boundary

> **Work mode outranks scope.** This skill is the `initial` (first-time discovery) review for a PR, branch, or merge diff. If the request is a recheck of prior findings, a second or final review, a final approval or sign-off decision, or evidence-first verification of specific claims, raw data, or a non-Git directory, stop and use `evidence-first-review` **even though the scope is a PR or branch**: this skill has no recheck or approval mode and would return newly discovered findings instead of the per-finding statuses (`resolved` / `partially resolved` / `unresolved` / `regressed`) and the approval verdict (`approved` / `conditionally approved` / `hold`) the user asked for. A read-only or no-changes constraint changes neither axis; it only constrains how the selected skill runs.
>
> **Committed scope only.** Step 1 collects files from `git log "$BASE_REF"..HEAD --no-merges` and diffs against `HEAD`, so staged, unstaged, and untracked work is invisible to this skill and it can abort with "No commits from this branch detected. Nothing to review." A request to review the entire uncommitted working state ("지금 작업 중인 변경 전체를 검토해줘") must therefore not run here. Enumerate the changed paths first with `git status --porcelain=v1 -z --untracked-files=all`, confirm the list with the user, and review those current files with `code-quality-review` or `web-security-review`, whichever matches the subject. These rules keep that list accurate:
>
> - Keep `--untracked-files=all`: the default collapses a newly created directory to one `dir/` line and never names the files inside it, and `git diff --name-only HEAD` alone lists no untracked file at all — either spelling silently drops new work from the review.
> - Read the records with `-z` and `while IFS= read -r -d ''`; never strip the status code with `| cut -c4-`. Newline-separated porcelain writes a rename as one `R  "old" -> "new"` line and quotes/escapes paths containing spaces or non-ASCII characters, so the cut output names paths that do not exist. `-z` never quotes a path; only rename/copy entries use two NUL fields (`XY new\0previous\0`), so consume the previous-path record after an `R` or `C` status — and test **both** status columns, `case "$status" in *R*|*C*)`, since the status is exactly two characters (X for the index, Y for the worktree). A worktree-side rename reports ` R` with a blank first column — reproduce it with a filesystem `mv` followed by `git add -N <new path>`, not with `git mv` then `git add -N`, which yields `R ` (a staged rename) because `git mv` has already updated the index and the trailing `git add -N` does nothing. A first-column-only pattern like `R*|C*` never consumes ` R`'s previous-path record; that record is then read as the next entry's path and a path that does not exist enters the review list.
> - **Route on one question — is exactly one status column filled? — and abort otherwise. Do not enumerate pairs.** When only X is filled (`M `, `A `, `R `, `T `, `D `) the worktree matches the index; when only Y is filled (` M`, ` A`, ` R`, ` T`, ` D`) the index matches HEAD. Either way the file on disk *is* what a commit would record, so it can go to a content-based reviewer. `??` (untracked) also passes, and `D `/` D` are pure deletions routed to the deletion path below. **When both columns are filled, stop the review**: print the raw `XY<space>path` records and ask the user to commit, stash, or resolve the conflict before asking again. Never skip such a path silently — silence is exactly how staged work vanishes from a review. Express the rule with negated character classes rather than a pair list — `' '[!\ ]` and `[!\ ]' '` — so no combination can be left out and any status letter Git adds later is covered.
> - **Both columns filled means the index and the worktree can hold different content, and reviewing the current file then misses the entire commit.** Measured on a real repository: for `MM` (dangerous edit staged, then the worktree reverted to the HEAD content) `git diff HEAD -- <path>` is **completely empty** while `git diff --cached HEAD -- <path>` still shows the removed `htmlspecialchars()` call — a current-content review sees nothing at all. For `AM` (dangerous new file staged, then overwritten with harmless content) the HEAD diff shows only the harmless side. For `AD` the HEAD diff is empty although `git commit` would add the file; for `RD` the HEAD diff names the **old** path so the new path yields nothing; for `MD` the HEAD diff shows a pure deletion and hides the staged modification. The old enumerated allowlist `[ MARCT][ MTRC]` passed `MM`, `AM`, `RM` and `MT` straight into the review, which is exactly this defect. Every unmerged pair (`DD`, `AU`, `UD`, `UA`, `DU`, `AA`, `UU`) fills both columns and so fails the same test; a leading `*U*` case states that intent explicitly.
> - **Aborting is right for this skill; reviewing the two sides separately is not.** The reviewers dispatched here (`code-quality-review`, `web-security-review`) inspect files on disk by path, and the index-side content is not a file — surfacing it would mean writing `git show :<path>` to a temporary file, after which every finding cites a path and line number that does not exist in the repository. Passing the gate is what establishes the single premise "the current file is what will be committed"; reviewing both sides breaks it and leaves the user unable to tell which of two reports describes the code that ships. Keep it practical by naming the remedy in the abort message instead: measured, a single `git add -A` collapsed `MM`, `AM`, `RM`, `MT`, `AD`, `RD` and `MD` all into one-column states. Note that `git add` adopts the **worktree** side and discards index-only content (for `MM` the record disappears entirely), so recovering the index side needs a commit or `git stash` — a choice only the user can make, which is why the gate does not make it for them.
> - A `D ` or ` D` status has no current content, so it must not go to a content-based reviewer — but it must not be dropped either. Review each deletion through `git diff HEAD -- <path>` and treat the removed lines as findings, the same way the security reviewer receives every changed path including deletions here: a removed CSRF check, auth guard, input sanitizer, or CSP header is itself a finding.
>
> ```bash
> CONTENT=(); DELETED=(); BLOCKED=()
> while IFS= read -r -d '' entry; do
>   status=${entry:0:2}; path=${entry:3}          # safe only because -z never quotes a path
>   case "$status" in *R*|*C*) IFS= read -r -d '' _previous || _previous="" ;; esac
>   case "$status" in
>     '??')              CONTENT+=("$path") ;;    # untracked
>     *U*)               BLOCKED+=("$status $path") ;;   # unmerged
>     'D '|' D')         DELETED+=("$path") ;;    # review via git diff HEAD -- <path>
>     ' '[!\ ]|[!\ ]' ') CONTENT+=("$path") ;;    # exactly one column filled → disk = what commits
>     *)                 BLOCKED+=("$status $path") ;;   # both columns filled (MM/AM/RM/MT/AD/RD/MD…)
>   esac
> done < <(git status --porcelain=v1 -z --untracked-files=all)
> if [ ${#BLOCKED[@]} -gt 0 ]; then
>   printf 'Cannot review the working tree — %d path(s) where the index and worktree disagree:\n' "${#BLOCKED[@]}"
>   printf '  %s\n' "${BLOCKED[@]}"
>   echo 'Run `git add <path>` to collapse them (this adopts the worktree side), or commit, stash, or resolve the conflict, then request the review again.'
>   exit 1
> fi
> ```
>
> Splitting the buckets by command works too, **but only after that gate has passed**: `git diff --name-only -z --diff-filter=d HEAD` (content scope; a rename yields only the new path) plus `git ls-files -z --others --exclude-standard` (untracked), and `git diff --name-only -z --diff-filter=D HEAD` for the diff-reviewed deletions. Lowercase `d` *excludes* deletions and therefore reproduces the loop's content rule; do **not** write `--diff-filter=ACMR` there, because it drops `T` (type change — a regular file swapped for a symlink or submodule) and silently removes that path from the review. An enumerated filter needs at least `ACMRT`. The two approaches agree only on the one-column states the gate admits — measured on a repository holding every such state, including ` A` (intent-to-add) and both `T` spellings, the command split and the status loop produced identical sorted sets. During an unresolved merge they diverge and **neither** is usable, so the gate must abort rather than fall back to the status loop: measured on a modify/delete conflict, `DU` appears in the `--diff-filter=d` bucket, `UD` appears in **neither** bucket, and `AA` also lands in `d` — and the status loop cannot tell which side's content is authoritative either. Sort both outputs and compare them before claiming they yield the same set.

## Reference Files

- `references/reviewer-prompts.md` — Common Instructions and the dispatch prompt templates (Step 2)
- `references/consolidated-report-template.md` — structure of the consolidated report (Step 5)

---

## Step 1: Collect Changed Files

Run the following to detect the base branch and list changed files:

```bash
# Auto-detect base branch: explicit priority — main → master → develop
# Use the full ref (origin/main) when available so git merge-base works
# even when no local tracking branch exists.
BASE_REF=""
BASE_LABEL=""
for candidate in origin/main origin/master origin/develop main master develop; do
  if git show-ref --verify --quiet "refs/remotes/${candidate}" 2>/dev/null; then
    BASE_REF="$candidate"
    BASE_LABEL="${candidate#origin/}"
    break
  elif git show-ref --verify --quiet "refs/heads/${candidate}" 2>/dev/null; then
    BASE_REF="$candidate"
    BASE_LABEL="$candidate"
    break
  fi
done
if [ -z "$BASE_REF" ]; then
  echo "ERROR: Could not detect base branch. Please specify manually (e.g., 'review against staging')."
  exit 1
fi

CURRENT=$(git rev-parse --abbrev-ref HEAD)
MERGE_BASE=$(git merge-base "$BASE_REF" HEAD)
echo "Base: $BASE_LABEL  →  Current: $CURRENT"
echo "Merge base: $MERGE_BASE"

# Collect only files touched by non-merge commits on this branch.
#
# Why not "git diff MERGE_BASE HEAD"?
# - If the developer merged main into the branch mid-work (e.g., to resolve conflicts),
#   git diff would include all files that changed in main as well.
# - If merge-base is recomputed after that mid-work merge, commits before the merge
#   would drop out of scope.
#
# Using --no-merges on git log ensures we see only the developer's own commits,
# regardless of mid-branch merges from main.
ALL_TOUCHED=$(git log "$BASE_REF"..HEAD --no-merges --name-only --format="" | sort -u | grep -v '^$')

# Quality reviewers: exclude deleted files.
# Lowercase "d" EXCLUDES only D, so every other status — including T (type change,
# e.g. a regular file replaced by a symlink) — stays in scope. Never enumerate
# ACMR here: it silently drops T. (Measured: a security.conf turned into a symlink
# is present with --diff-filter=d and absent with --diff-filter=ACMR.)
CHANGED_QA=$(echo "$ALL_TOUCHED" | while read -r f; do
  git diff --name-only --diff-filter=d "$MERGE_BASE" HEAD -- "$f" 2>/dev/null
done | sort -u)

# Security reviewer: every changed path, deletions included.
# No --diff-filter at all — the security scope is "everything", so an enumerated
# filter can only lose statuses (ACMRD lost T in the same measurement).
CHANGED_SEC=$(echo "$ALL_TOUCHED" | while read -r f; do
  git diff --name-only "$MERGE_BASE" HEAD -- "$f" 2>/dev/null
done | sort -u)

echo ""
echo "Files touched by this branch (excluding merge commits):"
echo "$ALL_TOUCHED"
echo ""
echo "Quality scope (non-deleted): $CHANGED_QA"
echo "Security scope (incl. deleted): $CHANGED_SEC"

# Early exit if nothing to review
if [ -z "$ALL_TOUCHED" ]; then
  echo "No commits from this branch detected. Nothing to review."
  exit 0
fi
```

Native Windows PowerShell equivalent (keeps the same branch-only scope and restores the caller's error preference):

```powershell
$previousErrorPreference = $ErrorActionPreference
try {
  $ErrorActionPreference = 'Stop'
  $candidates = @('origin/main', 'origin/master', 'origin/develop', 'main', 'master', 'develop')
  $baseRef = $null
  foreach ($candidate in $candidates) {
    git rev-parse --verify --quiet $candidate 2>$null
    if ($LASTEXITCODE -eq 0) { $baseRef = $candidate; break }
  }
  if (-not $baseRef) { throw 'Could not detect base branch; ask the user to specify one.' }

  $baseLabel = $baseRef -replace '^origin/', ''
  $current = (git rev-parse --abbrev-ref HEAD).Trim()
  $mergeBase = (git merge-base $baseRef HEAD).Trim()
  $allTouched = @(git log "$baseRef..HEAD" --no-merges --name-only --format='' |
    Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Sort-Object -Unique)
  # Same rule as the Bash block: lowercase 'd' excludes only deletions (keeps T),
  # and the security scope takes no --diff-filter at all.
  $changedQa = @($allTouched | ForEach-Object {
    git diff --name-only --diff-filter=d $mergeBase HEAD -- $_
  } | Sort-Object -Unique)
  # Rename pairs: `R100<TAB>previous<TAB>new`. Field 2 is the **previous** path — field 3 is
  # the new one, which is already in scope. Collecting the wrong field leaves the vanished
  # context invisible.
  $renamed = @(git diff --name-status --diff-filter=R -M $mergeBase HEAD |
    ForEach-Object { ($_ -split "`t")[1] } | Where-Object { $_ })
  $changedSec = @(@($allTouched | ForEach-Object {
    git diff --name-only $mergeBase HEAD -- $_
  }) + $renamed | Sort-Object -Unique | Where-Object { $_ })
} finally {
  $ErrorActionPreference = $previousErrorPreference
}
```

**How the file list is determined**:
- `git log "$BASE_REF"..HEAD --no-merges` collects only the developer's own commits — mid-branch merges from main are excluded, so files that changed only due to an upstream merge never enter the review scope.
- `MERGE_BASE` is used solely as the diff base when generating patch content (current state vs. divergence point).
- Quality reviewers (A/C) receive `CHANGED_QA` — `--diff-filter=d` excludes deletions and nothing else, so type changes (`T`) stay in scope.
- Security reviewer (B) receives `CHANGED_SEC` — no `--diff-filter`, so every changed path is included, deletions among them (a removed security guard is itself a finding).
- Never replace either filter with an enumerated list such as `ACMR`/`ACMRD`: both drop `T`, so a config file swapped for a symlink disappears from the review while `ALL_TOUCHED` still lists it.

Categorize the file list. **Extension decides the category wherever it can**, because a
manifest-based rule silently drops repositories that have no manifest — a legacy PHP project
without `composer.json` is common, and losing it would drop backend review entirely.

| Category | Extensions / Filenames | Decided by |
|----------|------------------------|---|
| **Backend (PHP)** | `*.php`, `composer.json`, `composer.lock` | extension alone |
| **Backend (Python)** | `*.py`, `pyproject.toml`, `requirements*.txt` | extension alone |
| **Backend (Go)** | `*.go`, `go.mod`, `go.sum` | extension alone |
| **Backend (Rust)** | `*.rs`, `Cargo.toml`, `Cargo.lock` | extension alone |
| **JS/TS** | `*.js`, `*.mjs`, `*.cjs`, `*.ts`, `*.mts`, `*.cts`, `*.tsx`, `package.json`, `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock` | **surface, see below** |
| **Frontend (markup)** | `*.svelte`, `*.html` | extension alone |
| **Style** | `*.css`, `*.scss`, `*.sass` | extension alone |
| **Config** | `*.json`, `*.yaml`, `*.yml`, `*.env*`, `*.ini` | extension alone |

**Only JS/TS needs a surface decision for the *quality* category**, because the same extension
serves a browser bundle and an HTTP server. Every other language's quality category is settled by
extension.

**Surfaces are still assigned to every language**, because they select security references. A
PHP app that emits HTML carries the `browser` surface — `*.php` templates with markup, or PHP
that echoes into a page — and its security review loads `browser-security.md` alongside
`php-backend-security.md`. A PHP service that only returns JSON does not.

A library with no `bin` entry, no server, and no bundler has **no surface evidence at all**. Do
not default it to `native`: mark it `ambiguous` and dispatch conservatively (below), because the
consumer decides the real surface and the consumer is not in this diff.

### Deciding the JS/TS surface

Judge **per workspace, not per repository** — a monorepo with a web app and a CLI is exactly the
case a single project-level verdict gets wrong. For each changed JS/TS file, find the nearest
enclosing `package.json` and read it:

| Surface | Evidence |
|---|---|
| `browser` | bundler config (Vite, webpack, Rollup, esbuild), a frontend framework dependency, `*.svelte`/`*.html` siblings, a `browser` field |
| `http-server` | a server framework dependency (Express, Fastify, NestJS, Koa, Hono), an HTTP listener, a `main`/`exports` server entry |
| `native` | a `bin` entry, a CLI framework dependency, or a process that reads argv/stdin/config from the working directory |

A workspace can carry more than one surface; assign all that apply. Path convention
(`apps/web`, `server/`, `src/routes`) is **supporting evidence only** — a manifest outranks it.

**When no `package.json` encloses the file at all** — a loose script, a build helper, a deleted
path whose workspace is gone — there is no manifest to read, so path convention and the file's
own contents become the only evidence. That is exactly the ambiguous case below: it does not
license skipping the file.

**When the surface is ambiguous, dispatch conservatively rather than asking.** Reviewers return
their findings in a single response and cannot pause for a question mid-run, so a question here
would stall the whole review:

- send the file to the **Node** quality reviewer in every ambiguous case;
- **also** send it to the frontend reviewer when a browser surface remains possible;
- tell the Security reviewer to load **every surface reference** for those paths
  (`http-server-security.md`, `browser-security.md`, `native-security.md`) — the same conservative
  rule the `web-security-review` selection table states for a library with no surface evidence;
- record `surface classification: ambiguous` for those paths in the final report;
- ask before dispatching only when even conservative duplication is impossible.

If no files match a category, skip the corresponding reviewer's scope (but the Security reviewer always reviews everything).

### Renamed and deleted paths

A rename yields only the new path (see Step 1), so a `.php` file renamed to `.ts` loses its PHP
context exactly when that matters most — an auth guard that vanished during the move. For every
rename in the branch, add the **previous path** to `CHANGED_SEC` and classify it by its own
extension, so the security reviewer still sees the old contents in the diff:

```bash
# Rename pairs on this branch: previous path <TAB> new path
RENAMES=$(git diff --name-status --diff-filter=R -M "$MERGE_BASE" HEAD | cut -f2)
CHANGED_SEC=$(printf '%s\n%s\n' "$CHANGED_SEC" "$RENAMES" | sort -u | grep -v '^$')
```

Deleted paths are already in `CHANGED_SEC` (no `--diff-filter`) and stay classified by
extension — a deleted `.php` is still PHP for security purposes even though no current file
exists to read.

---

## Step 2: Dispatch Reviewers in Parallel

Dispatch every agent **in a single message** (parallel Agent tool calls). Do not wait for one before starting the others.

The roster is **variable, not fixed at three**. Create **one quality reviewer per detected
backend language**, plus one frontend quality reviewer when a browser surface exists, plus one
security reviewer. A single "Backend Quality" slot would let a PHP+Node repository lose one
language entirely — whichever reviewer filled the slot last.

Read `references/reviewer-prompts.md` and use its Common Instructions block plus the prompt
templates verbatim. Invariants that must survive any adaptation:

| Agent | Skill invoked | Scope |
|---|---|---|
| **Quality — {language}** | `code-quality-review` with that language's reference | That language's files (`CHANGED_QA`) |
| **Security** | `web-security-review` with the references its surfaces select | ALL changed files, deleted included (`CHANGED_SEC`) |
| **Frontend Quality** | `code-quality-review` (`js-toolchain.md`, `js-frontend-quality.md`, `css-quality.md`) | Browser-surface + Style files (`CHANGED_QA`) |

One reviewer per language, and **each reviewer's file list is disjoint from the others'** —
except for the deliberate duplication an ambiguous JS/TS surface produces. Never merge two
languages into one reviewer to keep the count down: a persona and reference chosen for one
language produce confident, wrong findings about the other.

When a language has no reference file yet, do not substitute another language's. Skip that
language, name the unreviewed paths in the report, and let the remaining reviewers run.

- Every prompt embeds the Common Instructions, with `[OUTPUT_LANGUAGE]` replaced by the language the user used when requesting the review.
- Every reviewer is read-only: never modify a file, never write a report file to disk, never offer fixes. Results reach the team leader as the agent's **return value**, not through a file.
- Each prompt carries the reviewer's file list and the git diff for that list (`git diff "$MERGE_BASE" HEAD -- <files>`), plus the workspace root and base/merge-base/current refs.

---

## Step 2.5: Scope Decision Table

Before dispatching, decide which agents to spawn:

| Condition | Action |
|-----------|--------|
| A language's files == 0 | Skip that language's quality reviewer; note "No {language} changes" in report |
| Frontend + Style files == 0 | Skip the frontend quality reviewer; note "No frontend changes" in report |
| All changed files == 0 | Abort: "No changed files to review" |
| Security reviewer | Always spawn — reviews all changed files including deleted |

---

## Step 3: Wait for All Reviewers

Wait until all spawned agents have returned their complete reports. Do not prompt them for interim updates.

**Failure handling**:
- If an agent does not respond within a reasonable time, note it as `⚠ Reviewer did not complete` in the final report and proceed with partial findings.
- If an agent returns an error, retry once. If it fails again, mark that reviewer as unavailable.
- Never block the entire report waiting for one reviewer indefinitely.

**Completion gate — a language whose review did not happen cannot be approved.** Proceeding with
partial findings is right for *reporting*; it is wrong for the *verdict*. For every language with
changed files, `Ready to merge` **must not** be selected when any of these holds:

- its quality reviewer **did not complete** or returned an error twice;
- its quality reviewer was **not dispatched** at all — no reference file, or an ambiguous surface
  that never resolved;
- the security reviewer ran without the **reference for that language being loaded**.

In any of those cases the recommendation is `Block merge` or `Merge after fixes`, and the report
says which language went unreviewed and why. Silence about a missing reviewer reads as a clean
result, and the risk grows precisely as the roster grows — with one fixed backend reviewer a
failure was obvious; with one per language it is not.

> **Languages covered today** — each has both a quality reference and a security language-axis
> reference, so none of them is blocked by this gate: **PHP, Python, Go, Rust, and JS/TS**
> (server and browser surfaces). The surface-axis files `http-server-security.md`,
> `browser-security.md`, and `native-security.md` pair with all of them except PHP, which carries
> its HTTP surface in its own file.
>
> The gate still applies to any **other** language in the diff. For those, report the paths as
> unreviewed and let the recommendation reflect it, rather than approving a review that never
> loaded a reference for the changed language.
>
> Adding a language means four edits, not one — the quality reference and its row in
> `code-quality-review`, the security reference and its rows in the `web-security-review`
> selection table, the `{language} → {reference} → {scope}` and `{focus}` rows in
> `references/reviewer-prompts.md`, and the classification row in Step 1. Missing one of them
> fails silently: the reference exists but nothing loads it.

---

## Step 4: Team Leader Cross-Validation

After all reports are received:

**4a. Normalize quality finding severity** — quality reviewer reports use category-based format, not severity grades. Before cross-validating, assign each quality finding a severity:
- **High**: N+1 queries, broken auth logic, data corruption risk
- **Medium**: Eval-order issues, non-trivial duplication, performance anti-patterns in hot paths
- **Low**: Style inconsistencies, dead code, redundant comments

**4b. Cross-validate Critical and High findings** — run grep against the implicated file(s) only (not the whole project). For each finding, select the matching pattern family.

**Select the family by the implicated file's language, not by the list below being the only one.**
The patterns shipped here cover PHP, Python, Go, Rust, and the browser surface. When a finding lands in a language
with no family here, say `⚠ Needs runtime/architectural verification` rather than forcing a
mismatched pattern — a PHP injection regex run over Go proves nothing about the Go code, and a
non-match must never be read as evidence of safety. Adding a language means adding a family to
**both** the POSIX block and the PowerShell hashtable below; updating only one leaves Windows
installs silently behind.

**Security patterns** (from `web-security-review/references/`):
```bash
# Use -P for Perl-compatible regex (\s, alternation groups) — required on GNU grep

# SQL injection
grep -rnP "query\s*\(\s*[\"'].*\$" --include="*.php" <implicated_files>
grep -rnP "\.\s*\$_(GET|POST|REQUEST|COOKIE)" --include="*.php" <implicated_files>

# XSS
grep -rnP "echo \$_(GET|POST|REQUEST|COOKIE|SERVER)" --include="*.php" <implicated_files>
grep -rnP "innerHTML\s*=" --include="*.js" --include="*.svelte" <implicated_files>

# CSRF — check for missing token validation on state-changing endpoints
grep -rn "\$_POST\[" --include="*.php" <implicated_files> | grep -iv "csrf"

# Session security
grep -rn "session_start" --include="*.php" <implicated_files>
grep -rn "session_regenerate_id" --include="*.php" <implicated_files>

# File upload
grep -rnP "move_uploaded_file|\\\$_FILES" --include="*.php" <implicated_files>

# Hardcoded secrets
grep -rnP "password\s*=\s*['\"][^'\"]{3,}" --include="*.php" --include="*.js" <implicated_files>
grep -rnP "api_key|secret_key|access_token" --include="*.env" --include="*.json" <implicated_files>

# Frontend sinks
grep -rnP "\.html\(|\.append\(|\.prepend\(" --include="*.js" <implicated_files>
grep -rn "{@html" --include="*.svelte" <implicated_files>
grep -rnP "localStorage|sessionStorage" --include="*.js" --include="*.svelte" <implicated_files>

# Python — injection sinks, unsafe deserialization, template escape hatches, weak randomness
grep -rnP 'execute\(f["'"'"']|execute\(.*%\s*\(|\.raw\(|\.extra\(' --include="*.py" <implicated_files>
grep -rnP "shell\s*=\s*True|os\.system|os\.popen" --include="*.py" <implicated_files>
grep -rnP "pickle\.loads?|yaml\.load\(|\beval\(|\bexec\(" --include="*.py" <implicated_files>
grep -rnP "mark_safe|\|safe|Markup\(|Template\(" --include="*.py" <implicated_files>
grep -rnP "random\.(choice|randint|choices)|md5\(|sha1\(|verify\s*=\s*False" --include="*.py" <implicated_files>

# Go — shell re-entry, formatted SQL, the wrong template package, weak randomness
grep -rnP 'exec\.Command\("(sh|bash|cmd|powershell)"' --include="*.go" <implicated_files>
grep -rnP "(Query|Exec|QueryRow)\w*\(\s*fmt\.Sprintf" --include="*.go" <implicated_files>
grep -rn '"text/template"' --include="*.go" <implicated_files>
grep -rnP "math/rand|InsecureSkipVerify|crypto/(md5|sha1)" --include="*.go" <implicated_files>

# Rust — reachable panics, formatted SQL, shell re-entry, unsafe, TLS bypass
grep -rnP "\.unwrap\(\)|\.expect\(" --include="*.rs" <implicated_files>
grep -rnP "query\(&?format!|sql_query\(|execute\(&?format!" --include="*.rs" <implicated_files>
grep -rnP 'Command::new\("(sh|bash|cmd|powershell)"' --include="*.rs" <implicated_files>
grep -rnP "unsafe\s*\{|from_raw_parts|get_unchecked|transmute" --include="*.rs" <implicated_files>
grep -rnP "danger_accept_invalid_certs|SmallRng|seed_from_u64" --include="*.rs" <implicated_files>
```

`.unwrap()` in Rust is the one pattern here that matches far more than it should — it is
idiomatic in `main`, tests, and benches. Use it to locate the flagged line, never as
corroboration on its own.

**Quality patterns** (from `code-quality-review/references/`):
```bash
# N+1 / query inside loop (use as signal; confirm manually — 3-line window misses service calls)
grep -rn "foreach\|for " --include="*.php" -A3 <implicated_files> | grep -i "query\|prepare\|execute"
grep -rn "for.*count(" --include="*.php" <implicated_files>
grep -rn "SELECT \*" --include="*.php" <implicated_files>

# Manual Svelte subscribe without cleanup
grep -rn "\.subscribe(" --include="*.svelte" <implicated_files>

# Python / Go / Rust quality signals (confirm manually — a window match is not a finding)
grep -rnP "except\s*:|except Exception" --include="*.py" <implicated_files>
grep -rnP "def \w+\([^)]*=\s*(\[\]|\{\})" --include="*.py" <implicated_files>
grep -rn "for " --include="*.go" -A3 <implicated_files> | grep -P "defer |\.Query\(|http\.Get"
grep -rnP ":?=\s*_\s*,|,\s*_\s*:?=" --include="*.go" <implicated_files>
grep -rnP "std::(fs|thread::sleep)|\.lock\(\)" --include="*.rs" <implicated_files>

# CSS issues
grep -rn "!important" --include="*.css" --include="*.scss" <implicated_files>
```

On native Windows, cross-validate only the implicated files with `rg` or this PowerShell fallback; do not scan the whole repository:

```powershell
$implicatedFiles = @('path\to\flagged-file.php', 'src\Flagged.svelte')
$patternFamilies = [ordered]@{
  SqlInjection = @('query\s*\(\s*["''].*\$', '\.\s*\$_(?:GET|POST|REQUEST|COOKIE)')
  Xss = @('echo\s+\$_(?:GET|POST|REQUEST|COOKIE|SERVER)', 'innerHTML\s*=', '\.html\(', '\.append\(', '\.prepend\(', '\{@html')
  Csrf = @('\$_POST\[') # manually confirm that no CSRF validation protects the endpoint
  Session = @('session_start', 'session_regenerate_id')
  Upload = @('move_uploaded_file', '\$_FILES')
  Secrets = @('password\s*=\s*["''][^"'']{3,}', 'api_key', 'secret_key', 'access_token')
  BrowserStorage = @('localStorage', 'sessionStorage')
  BackendQuality = @('foreach', 'for\s*\(', 'query', 'prepare', 'execute', 'for.*count\(', 'SELECT\s+\*')
  FrontendQuality = @('\.subscribe\(', '!important')
  PythonSecurity = @('execute\(f["'']', '\.raw\(', '\.extra\(', 'shell\s*=\s*True', 'os\.system', 'os\.popen', 'pickle\.loads?', 'yaml\.load\(', 'mark_safe', 'Markup\(', 'random\.(?:choice|randint|choices)', 'verify\s*=\s*False')
  GoSecurity = @('exec\.Command\("(?:sh|bash|cmd|powershell)"', '(?:Query|Exec|QueryRow)\w*\(\s*fmt\.Sprintf', '"text/template"', 'math/rand', 'InsecureSkipVerify')
  RustSecurity = @('\.unwrap\(\)', '\.expect\(', 'query\(&?format!', 'sql_query\(', 'Command::new\("(?:sh|bash|cmd|powershell)"', 'unsafe\s*\{', 'from_raw_parts', 'get_unchecked', 'transmute', 'danger_accept_invalid_certs')
  PythonQuality = @('except\s*:', 'except Exception', 'def \w+\([^)]*=\s*(?:\[\]|\{\})')
  GoQuality = @('defer ', ':?=\s*_\s*,', ',\s*_\s*:?=')
  RustQuality = @('std::fs', 'std::thread::sleep', '\.lock\(\)')
}
$files = Get-ChildItem -LiteralPath $implicatedFiles -File -ErrorAction SilentlyContinue
foreach ($family in $patternFamilies.GetEnumerator()) {
  $files | Select-String -Pattern $family.Value -CaseSensitive:$false |
    ForEach-Object { '[{0}] {1}:{2}: {3}' -f $family.Key, $_.Path, $_.LineNumber, $_.Line.Trim() }
}
```

**4c. Mark each Critical/High finding**:
- `✓ Pattern corroborated` — grep confirmed the suspicious pattern in the file
- `✓ Manually confirmed` — reviewed in context; vulnerability/bug confirmed
- `⚠ Needs runtime/architectural verification` — grep inconclusive or pattern is absence-based (e.g., missing CSRF check); cannot confirm via static analysis alone

**4d. Documented-intent re-check** — for each Critical/High finding, read the flagged line and its enclosing function in the actual file:
- If a comment explicitly acknowledges the flagged behavior as intentional (states the why) and the finding is **not** in a non-downgradable class (injection, XSS, CSRF, SSRF, path traversal, secrets/internal-information exposure, auth bypass/privilege escalation, RCE/unsafe deserialization, data loss/corruption incl. irreversible race/idempotency defects), **downgrade it to Low/Informational** and record the reason as `문서화된 의도 — "[comment excerpt]"`. It moves to the Low/Informational section — do not drop it entirely.
- If the finding **is** in a non-downgradable class, keep the original severity and add a note that an intent comment exists.
- Also verify the reverse: if a reviewer downgraded a non-downgradable-class finding because of a comment, restore its original severity.
- A generic or unrelated nearby comment does not qualify — the comment must address the specific flagged risk.

---

## Step 5: Produce Consolidated Report

**Language**: Write the report in the same language the user used when requesting the review ([OUTPUT_LANGUAGE] from Step 2). Apply this to all sections including findings, recommendations, and the executive summary.

**Translation safety net**: Reviewer agents sometimes return findings in English despite instructions. When consolidating, NEVER copy reviewer prose verbatim into the report if it is not in [OUTPUT_LANGUAGE] — translate finding titles, impact statements, and recommendations into [OUTPUT_LANGUAGE] yourself. Keep code identifiers, file paths, severity grades (Critical/High/Medium/Low), and quoted evidence snippets as-is. The Appendix (raw reviewer reports) is exempt — include it unedited.

Before finalizing, scan the consolidated sections (everything above the Appendix): if any finding title, impact, or recommendation is still in the wrong language, translate it before emitting or handing off the report.

**Delivery — inline by default.** Emit the consolidated report in your response. Do **not** create `.tasks/reports/` and do not write a report file: a review request must not change the working tree or add commit candidates.

**Write a file only on an explicit request** — "리포트로 만들어줘", "보고서로 출력해줘", "리포트 파일로 저장해줘", "output as a report", or an equivalent explicit ask for a saved report. In that case do not choose a path or write the file here — **delegate to the `report-output` skill** and pass the finished consolidated report plus:

- **slug**: the current branch name in kebab-case with the `-branch-review` suffix — e.g. `feature-user-auth-branch-review`. Shorten a long or cryptic branch name to its meaningful part;
- **recommended format**: Markdown (mention HTML as an option only if the user asks).

`report-output` owns path selection, name-collision avoidance, and atomic publishing — this skill never writes under `.tasks/reports/` itself. That single owner matters here because this skill runs parallel reviewers, so several report-shaped outputs can be in flight at once. If `report-output` is not installed, say so and keep the report inline rather than improvising a path.

Follow the structure in `references/consolidated-report-template.md`.

**Finding identifiers**: the report is read by a person and its blocking-items line asks them to
decide, so `CH-1` alone is not enough. Invoke `readable-ids` if it is installed to register the
finding identifiers and render them as `CH-1(feature/label)` on first mention. The read-only rule
above is the one exception, since it forbids writing any file: there, render the labels inline and
create no registry. Without that skill,
still write a short label beside each identifier — a later recheck refers to these findings by
number across a different document, which is exactly where a bare number stops meaning anything.
