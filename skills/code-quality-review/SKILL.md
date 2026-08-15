---
name: code-quality-review
description: "Review code for quality and performance issues. Trigger when user asks for code quality review, refactoring advice, or code cleanup. Covers: (1) unnecessary or misleading comments, (2) style inconsistencies vs project conventions, (3) duplicated/redundant code, (4) performance inefficiencies — especially evaluation order (cheap checks before expensive ones). Covers PHP, JavaScript/TypeScript on both sides — browser code and Node services, CLIs, and libraries — and CSS/SCSS. Runs CLI tools automatically (PHPStan/phpcs/phpmd/phpcpd for PHP; ESLint/Biome/oxlint/tsc/svelte-check/knip for JS/TS; Stylelint for CSS/SCSS). Adapts per detected language and framework; a language with no reference here is reported as unsupported rather than checked against another language's rules. Do not use when the request names security as the subject (use web-security-review) or when the scope is a whole branch/PR before merge (use branch-merge-review)."
---

# Code Quality Review

Runs CLI analysis tools first, then supplements with pattern-based review. Adapts to the detected stack.

## Platform command selection

Detect the active shell before using a snippet. On POSIX use `command -v`, `[ -f ... ]`, and the Bash examples below. On Windows PowerShell use `Get-Command`, `Test-Path`, and PowerShell conditionals; invoke the same PHP/npm tools directly. Prefer `rg` for recursive searches on both platforms, with `Get-ChildItem -Recurse | Select-String` as the Windows fallback. Do not require WSL or Git Bash for a Windows-native installation.

> **Read-only mode (priority rule).** If the user asked for a review **without changing anything** (e.g. "수정하지 말고 검토만", "read-only", review delegated under a read-only sandbox), then this skill must not write to the workspace:
> - **Do not install** missing tools (no `npm install`, `composer require`, PHAR downloads, etc.). Run only the tools already present. Record the withheld install command as **`skipped-read-only`**, and the tool role it would have enabled as **`skipped-not-installed`** — the command was withheld, the check was impossible.
> - **Do not modify code** and do not change worktree or Git state — findings and recommendations only.
> - **Do not write any file**, report files included. (Inline output is the default anyway — see Step 4; under a read-only constraint it is the *only* option, even if the user asks for a file. Say that a report file needs write permission.)
>
> When in doubt, treat the request as read-only and ask before installing or writing.

## Reference Files

Load before scanning:
- `references/php-quality.md` — PHP tool setup, execution, and manual patterns
- `references/js-toolchain.md` — JS/TS toolchain and environment-neutral patterns (**single source for tool invocation**)
- `references/js-frontend-quality.md` — browser surface: DOM, jQuery, Svelte, HTMX
- `references/node-quality.md` — server, CLI, daemon, library: async, streams, lifecycle, resources
- `references/css-quality.md` — CSS/SCSS tool setup, execution, and manual patterns

Load all applicable files for full-stack review.

**If no reference exists for a detected language, report that language as unsupported and skip
its files — do not stop the whole review.** A mixed repository still gets a full PHP review when
its Go service has no reference yet; what must never happen is substituting another language's
rules, because a PHP checklist applied to Go produces confident findings about code it does not
understand. Name the unreviewed paths in the report so the gap is visible.

### What a language reference must contain

This is the **target contract** for new and restructured references. The five shipped today
predate it and do not match it yet — their current numbering is below. Restructuring them is
scheduled work, not a precondition for using this table.

| Reference | Current sections |
|---|---|
| `php-quality.md` | §0 version resolution · §1 setup · §2 execution · §3–6 manual patterns |
| `js-toolchain.md` | §1 setup · §2 execution · §3–5 neutral patterns |
| `js-frontend-quality.md` | §1 browser performance · §2 browser style/duplication · §3 Svelte lifecycle |
| `node-quality.md` | §1–7 server-side patterns |
| `css-quality.md` | §1 setup · §2 execution · §3–6 manual patterns |

The target: every `references/{language}-quality.md` carries the same seven sections so this
skill can drive it without knowing the language, and adding a language means adding one
reference file plus one detection row in Step 1 — not editing the body below.

| § | Contents |
|---|---|
| 0 | **Applicability and scope** — detection signals, package/workspace root, generated and vendor paths to exclude |
| 1 | **Version resolution** — runtime, toolchain, package manager, and lockfile the project pins |
| 2 | **Tool roles** — static analysis / style / complexity / duplication, and which project config takes precedence |
| 3 | **Availability and authority** — existence check, install path for normal mode, and the read-only contract below |
| 4 | **Execution** — POSIX and PowerShell 5.1 forms, exit-code and output interpretation, and any write side effect |
| 5 | **Manual patterns** — what the tools cannot catch |
| 6 | **Severity mapping** — tool output to High/Medium/Low, plus the run-state vocabulary below |

Do not force one tool per role. When a role has no established tool in that language, record
`not applicable` or `unavailable` with the reason instead of inventing one.

**Run-state vocabulary** — every tool invocation resolves to exactly one:

| State | Meaning |
|---|---|
| `passed` | Ran clean |
| `findings` | Ran and reported problems |
| `skipped-read-only` | A **command** writes, and the request is read-only, so it was withheld. This is what the contract line below records |
| `skipped-not-installed` | A **tool role** could not run because its tool is absent — under read-only because the install was withheld, in normal mode because the install failed |
| `unavailable` | No tool fills this role in this language |
| `timeout` / `execution-error` | Started but did not produce a usable result |

The two skip states describe **different things** and often co-occur: `skipped-read-only` is
about a command that was withheld, `skipped-not-installed` is about a role that produced no
findings. A read-only review of a machine without PHPStan records both — the install as
`skipped-read-only`, static analysis as `skipped-not-installed`. Collapsing them hides which
findings the review could still have produced with write permission.

An incomplete run never silently becomes a pass. State which run-states occurred, and treat any
of the last four as leaving that role **unverified** — the verdict must say so rather than
implying the code passed that check.

### Read-only contract for write-causing commands

A reference file may not quietly instruct a write that the read-only rule above forbids. Every
command that installs, creates a directory, sets a permission bit, initializes a tool, writes a
config or report file, or auto-fixes code carries one of these two lines:

```
**Read-only:** skip this command; record it as `skipped-read-only`.
**Read-only:** skip every command in this block; record them as `skipped-read-only`.
```

The first sits immediately above its command — as prose outside a fence, or as a `#` / `//`
comment inside one, so the example stays runnable. The second sits in the prose immediately
before a fence and covers every command in that block; it states its own scope, so it can never
be mistaken for a guard on one command while the rest run unguarded.

`tests/test_php_baseline.py` enumerates the write-causing commands in the references shipped
today and fails when one loses its contract line. It does not discover a new reference
on its own — **when you add a language, add its write-causing commands to that list too.**

**Always invoke npm-hosted tools as `npx --no -- <tool>`.** Plain `npx` falls back to downloading a
missing package into the npm cache, and [npm's docs](https://docs.npmjs.com/cli/commands/npx)
state that in non-TTY or CI environments `--yes` is assumed — so an agent running `npx eslint`
non-interactively installs silently, which a read-only review must never do. `--no` makes the
command fail instead. (`--no-install` is a deprecated alias that npm converts to `--no`; write
`--no` so the contract has one spelling.) Running the project-local binary directly is equally
acceptable — `node_modules/.bin/<tool>` on POSIX, `node_modules\.bin\<tool>.cmd` on Windows,
where the extensionless file is a shell script that does not execute.

**The `--` separator is not optional.** Without it npx claims flags it recognises before the tool
ever runs: `npx --no tsc --version` prints *npm's* version and exits `0` on a machine with no
TypeScript installed — a review would record that as a passing type check. `npx --no -- tsc
--version` fails loudly instead. Verified on both platforms (npm 11.16.0 on Linux, npm 11.12.1
under Windows PowerShell 5.1); neither left anything in the working directory. Everything after
`--` belongs to the tool.

## Step 1: Detect Stack and Infer Conventions

Inspect the project root to determine languages and frameworks:
- PHP: `composer.json`, `*.php` files → load `references/php-quality.md`
- JS/TS: `package.json`, `*.js`, `*.mjs`, `*.cjs`, `*.ts`, `*.mts`, `*.cts`, `*.tsx` → always load `references/js-toolchain.md`, then
  - browser surface (`*.svelte`, bundler config, a frontend framework dependency) → `references/js-frontend-quality.md`
  - server surface (a server framework dependency, a `bin` entry, an HTTP listener) → `references/node-quality.md`
  - both, when the workspace serves both
- CSS/SCSS: `*.css`, `*.scss`, `*.sass` files → load `references/css-quality.md`

Infer project conventions from **existing code majority** (not assumed standards):
- Naming style, indentation, quote style, comment format, component structure

## Step 2: Run CLI Tools

Run all applicable tools. For each tool, check if it exists first — if not, install per the reference file instructions. **Under read-only, the install command is withheld (`skipped-read-only`) and the tool role it would have enabled stays unrun (`skipped-not-installed`).** In normal mode, `skipped-not-installed` means the install itself failed. Capture output for integration into the report.

### PHP stack

`references/php-quality.md` is the **single source** for PHP toolchain invocation — runtime
version resolution (`PHP_CMD`), source-directory derivation (`SRC_DIR`), and the four tool
commands all live there. Follow its §0 for version resolution and §2 for execution.

Duplicating those commands here would drift: two spellings of the same instruction leave the
reader unable to tell which is authoritative, and only one of them gets fixed.

### JS / TypeScript stack

`references/js-toolchain.md` is the **single source** for JS/TS tool invocation — ESLint, Biome,
Oxlint, `tsc --noEmit`, svelte-check, and knip, each with its read-only contract. Follow its §2.

### CSS / SCSS stack

`references/css-quality.md` §2 owns Stylelint invocation.

Installation for every stack lives in its reference file's setup section, gated by the
read-only contract above.

## Step 3: Manual Review — Four Categories

After collecting tool output, perform pattern-based review to catch what tools miss.

### Category 1 — Unnecessary Comments
Flag: restate-the-code comments, commented-out dead code, stale TODOs.
Keep: explains "why", intentional workarounds with reason, correct docblocks.

### Category 2 — Style Inconsistencies
Flag deviations from the inferred project majority only — not from external standards.
Tools cover most of this; focus manual review on semantic inconsistencies tools can't detect
(e.g., same concept named differently in different files).

**Svelte lifecycle review rule**: Before flagging any store subscription or lifecycle issue in a `.svelte` file, read the entire component. The `$store` reactive syntax auto-unsubscribes — never flag it as a leak. Only flag manual `.subscribe()` calls that lack an `onDestroy` cleanup. See `references/js-frontend-quality.md` Section 3 for the full decision tree.

### Category 3 — Duplicated / Redundant Code
Tools (phpcpd, knip) cover structural duplication. Also flag:
- Near-identical SQL queries differing only in one parameter
- Copy-pasted validation logic tools don't detect as duplication

### Category 4 — Performance & Evaluation Order
Core principle: **cheapest check first** — short-circuit before expensive operations.
Tools don't catch evaluation order. Flag manually:
- DB/file I/O before null/type guard
- Regex before `str_contains` / `includes` pre-filter
- DOM query or heavy computation inside a loop (should be cached outside)
- N+1 query pattern
- Full fetch when only count/existence is needed

See reference files for language-specific examples.

### Documented Intent — Downgrade Rule

Before finalizing any finding, check the flagged line and its enclosing function for a comment that explicitly acknowledges the behavior as intentional (states the why — e.g., `// 의도적 중복: A/B 테스트 종료 후 제거 예정`, `// full fetch 필요: 후속 배치에서 전체 row 사용`). If such a comment exists, **downgrade the finding to Informational**, keep it in the report, and cite the comment (mark it `문서화된 의도`).

**Exception — never downgrade** findings that imply data corruption or silent data loss, race/idempotency defects with irreversible effects, or any security risk (injection, XSS, CSRF, SSRF, path traversal, secrets exposure, auth bypass, RCE/unsafe deserialization), regardless of comments. Note the comment's existence but keep the original severity.

The comment must address the specific flagged behavior; a generic nearby comment does not qualify. Intentional-looking behavior without a comment is reported at normal severity with a recommendation to add an explanatory comment.

## Step 4: Produce Report

**Language**: Write the report in the same language the user used when requesting the review. If the user wrote in Korean, write the report in Korean. If in English, write in English. **When running as a subagent** (e.g., dispatched by branch-merge-review), the invoking prompt's `OUTPUT LANGUAGE` directive takes precedence over the prompt's own language — an English dispatch prompt does NOT mean the report should be in English. Keep code identifiers, file paths, and evidence snippets as-is; write all prose in the designated language.

**Delivery — inline by default.** Emit the report in your response. Do **not** create `.tasks/reports/` and do not write a report file: a review request must not change the working tree or add commit candidates.

**Write a file only on an explicit request** — "리포트로 만들어줘", "보고서로 출력해줘", "리포트 파일로 저장해줘", "output as a report", "write this up as a report", or an equivalent explicit ask for a saved report. In that case do not choose a path or write the file here — **delegate to the `report-output` skill** and pass:

- the finished report body (the structure below) and its language;
- **slug**: short kebab-case identifier from the user's request or the target, max ~30 chars, with the `-quality` suffix — e.g. `user-auth-quality`;
- **recommended format**: Markdown (mention HTML as an option only if the user asks).

`report-output` owns path selection, name-collision avoidance, and atomic publishing — this skill never writes under `.tasks/reports/` itself. If `report-output` is not installed, say so and keep the report inline rather than improvising a path.

Merge tool output and manual findings into this structure.

```
# Code Quality Report
**Date**: [date]
**Scope**: [files/feature reviewed]
**Stack**: [detected language + framework]
**Tools run**: [list of tools executed]

## Executive Summary
[2–3 sentences: overall quality level, most critical findings]

## Tool Findings
[Summarised output from PHPStan / phpcs / phpmd / phpcpd / ESLint / knip / Stylelint etc.]
[Group by tool, strip noise, keep actionable items with file:line references]

## Style & Convention Issues    [S-N]
## Comment Quality Issues       [C-N]
## Duplication Issues           [D-N]
## Performance Issues           [P-N]
## CSS / SCSS Issues            [CSS-N]
  - Location, Issue (specificity / magic number / nesting / dead code), Impact, Suggestion
  - Location, Issue, Impact (low/medium/high), Suggestion

## Passed Checks
[Reinforce patterns done well]
```

## Step 5: Offer Fixes

If any finding overlaps with a security concern (SQL injection, XSS, hardcoded secrets, missing CSRF),
defer to the `web-security-review` skill — do not fix security issues here.

Fix quality findings one at a time: Performance → Duplication → CSS → Style → Comments.
Keep each fix minimal. Run tests after each change.
