---
name: code-quality-review
description: "Review code for quality and performance issues. Trigger when user asks for code quality review, refactoring advice, or code cleanup. Covers: (1) unnecessary or misleading comments, (2) style inconsistencies vs project conventions, (3) duplicated/redundant code, (4) performance inefficiencies — especially evaluation order (cheap checks before expensive ones). Covers PHP, Python, Go, Rust, JavaScript/TypeScript on both sides — browser code and Node services, CLIs, and libraries — and CSS/SCSS. Runs CLI tools automatically (PHPStan/phpcs/phpmd/phpcpd for PHP; ruff/mypy/pyright/vulture/radon for Python; go vet/staticcheck/golangci-lint/gofmt for Go; clippy/rustfmt for Rust; ESLint/Biome/oxlint/tsc/svelte-check/knip for JS/TS; Stylelint for CSS/SCSS). Adapts per detected language and framework; a language with no reference here is reported as unsupported rather than checked against another language's rules. Do not use when the request names security as the subject (use web-security-review) or when the scope is a whole branch/PR before merge (use branch-merge-review)."
---

# Code Quality Review

Runs CLI analysis tools first, then supplements with pattern-based review. Adapts to the detected stack.

## Platform command selection

Detect the active shell before using a snippet. On POSIX use `command -v`, `[ -f ... ]`, and the Bash examples below. On Windows PowerShell use `Get-Command`, `Test-Path`, and PowerShell conditionals; invoke the same PHP/npm tools directly. Prefer `rg` for recursive searches on both platforms, with `Get-ChildItem -Recurse | Select-String` as the Windows fallback. Do not require WSL or Git Bash for a Windows-native installation.

> **Read-only mode (priority rule).** If the user asked for a review **without changing anything** (e.g. "수정하지 말고 검토만", "read-only", review delegated under a read-only sandbox), then this skill must not write to the workspace:
> - **Do not install** missing tools (no `npm install`, `composer require`, PHAR downloads, etc.). Run only the tools already present. Record the withheld install command as **`skipped-read-only`**, and the tool role it would have enabled as **`skipped-not-installed`** — the command was withheld, the check was impossible.
> - **Do not modify code** and do not change worktree or Git state — findings and recommendations only.
> - **Do not write any file into the workspace**, report files included. (Inline output is the default anyway — see Step 4; under a read-only constraint it is the *only* option, even if the user asks for a file. Say that a report file needs write permission.)
>
> **Where the boundary is.** The workspace — the user's repository and anything under it — is what
> must come out unchanged. A tool writing its own cache to a process-temporary directory outside
> the workspace does not violate this, and some checks cannot run at all without one: cargo has to
> put build output somewhere, so `CARGO_TARGET_DIR` pointed at a temp directory is the read-only
> form, not an exception to it. **Where a genuinely write-free form exists, prefer it** — mypy's
> `--cache-dir=/dev/null` writes nothing anywhere, so use that rather than a temp directory.
> Never redirect a write out of the workspace to make a *code-modifying* command acceptable; that
> is a different rule and it has no exceptions.
>
> When in doubt, treat the request as read-only and ask before installing or writing.
>
> **A second, separate axis: does the tool *execute* the code under review?** Not writing files and
> not running attacker-controlled code are different guarantees, and the read-only flags above
> only buy the first. Measured in this repository:
>
> **The test is not the config's file format, and it is not "does it name an extension" either.**
> A declarative config executes code when it *names* code: `.eslintrc.json` is pure JSON, and
> `{"plugins": ["probe"]}` in it loads and runs `eslint-plugin-probe` — reproduced here, as was
> the same thing through `extends` in a `.stylelintrc.json`. But naming an extension is not
> sufficient either: Biome's `plugins` takes GritQL pattern files, which are a matching DSL, not
> host code.
>
> **The question is whether the analysis ends up calling host code or an external executable that
> the diff controls.** Answer it by resolving the whole chain before running:
>
> 0. **The repository replaces or wraps the tool itself** — this one sits above the others and
>    applies no matter which tool you run. Both reproduced here:
>    cargo config (`.cargo/config.toml` **or** the extensionless `.cargo/config`, both read) can
>    set `build.rustc` / `rustc-wrapper` / `rustc-workspace-wrapper`, a `linker`, a
>    `credential-provider`, **or an `[alias]` that shadows the subcommand itself** — `clippy` is
>    an *external* subcommand, so `[alias] clippy = "run --bin x"` makes `cargo clippy` build and
>    run a binary instead of linting, with no `build.rs` anywhere. (An alias cannot shadow a
>    built-in like `check`; both directions verified.) And an `.npmrc` carrying
>    `node-options=--require ./hook.js` injects that file into **every** npm-launched tool —
>    ESLint, Stylelint, tsc alike — regardless of their own configs.
>    The shape to look for is **anything that decides which executable actually runs**, not just
>    what that executable then reads.
>    Not every ecosystem has this: Go reads `GOFLAGS` only from the environment and the user's
>    `GOENV`, never from a file in the repository, and a repository-level `sitecustomize.py` is
>    not loaded by ruff or mypy (both verified). The question to ask is always **whether the diff
>    can control it**, not whether the mechanism exists.
> 1. **The config is a program** — `eslint.config.js`, `.stylelintrc.js`, `stylelint.config.mjs`
>    or `.ts`, a PHPStan `includes:` entry pointing at a `.php` file (reproduced: it runs).
> 2. **The config names host code** — `plugins`, `parser`, `processor`, `customSyntax`, an
>    `extends` that resolves to a package, mypy's `plugins`, PHPStan's `rules` / `services`.
> 3. **The manifest loads code behind the tool's back** — cargo runs `build.rs` and proc macros;
>    PHPStan loads the composer autoloader, which runs `autoload.files` **from the root package
>    and from every dependency** (reproduced). A PHPStan extension shipped by a dependency can be
>    activated by `phpstan/extension-installer` with nothing in the root config at all.
> 4. **Config chains hide all of the above** — `extends` and `includes` are recursive. A clean
>    root config that includes a second file proves nothing until you have followed it.
> 5. **The invocation itself** — flags like PHPStan's `-a/--autoload-file` load code too. Those
>    come from whoever runs the review, so they are yours to control; the point is that the
>    closure is over *config + manifest + chain + invocation*, not config alone.
>
> | Tool | Calls host code the diff controls? |
> |---|---|
> | `cargo clippy`, `cargo check` | **Yes**, by two independent routes: a `build.rs` or proc-macro dependency is compiled *and run* (a `build.rs` writing outside the workspace was reproduced on cargo 1.91.0), **and** `.cargo/config.toml` can set `build.rustc` / `build.rustc-wrapper` to any executable, which cargo then calls with no `build.rs` present (also reproduced) |
> | ESLint | **Yes** with a flat config, and with any config naming a plugin, parser, processor, or shared-config package |
> | Stylelint | **Yes** for a `.js`/`.mjs`/`.cjs`/`.ts` config, and for a JSON or `package.json` config naming `extends`, `plugins`, or `customSyntax` (both reproduced) |
> | mypy | **Yes if `[tool.mypy] plugins` is set** |
> | PHPStan | **Yes** for `bootstrapFiles`, project `rules`/`services`, a `.php` `includes:` entry, or composer `autoload.files` in the root **or any dependency** — see below |
> | Biome | **A weaker yes** — `plugins` loads local GritQL files. That is a pattern DSL, not host code: it can distort what the analysis reports, but it does not execute arbitrary commands. Treat it as a reason to read the plugin, not as a reason to sandbox |
> | `ruff` | No — a Rust binary with no plugin mechanism |
> | `go vet`, `staticcheck`, `gofmt` | No. Go has no build-time hook, cgo is compiled without running, and `-toolexec` — which *does* call an external program — can only arrive through the environment, which the diff does not control (all verified) |
> | `tsc` | No |
>
> So the safe answer is never "the config looks declarative". It is: **the resolved chain — the
> repository's tool-level settings, the config, its `extends`/`includes`, the manifest and
> lockfile, the autoloader, and the invocation — names no host code and no external executable
> that the diff controls.** Anything you have not resolved counts as unresolved, not as safe.
>
> **PHPStan's condition is narrow and worth stating exactly**, because the common case is safe.
> Measured on PHPStan 2.x with PHP 8.3, one file per case:
>
> | Setup | Runs the file? |
> |---|---|
> | `paths:` — the files being analysed | No. Analysis is static parsing |
> | `scanFiles:` | No |
> | `bootstrapFiles:` in the config | **Yes** |
> | project `rules:` / `services:` in the config | **Yes** — a project-defined rule or extension is a class PHPStan instantiates and calls during analysis |
> | an `includes:` entry pointing at a `.php` file | **Yes** — PHPStan supports PHP files as dynamic config and executes them (reproduced) |
> | `bootstrapFiles:` reached through `includes:` | **Yes** — the chain is recursive, so a clean root config proves nothing (reproduced) |
> | `composer.json` → `autoload.files`, root **or any dependency** | **Yes**, with nothing declared in `phpstan.neon`. The composer autoloader runs every entry in `vendor/composer/autoload_files.php`, which includes dependencies' own `autoload.files` (reproduced) |
>
> **On an untrusted diff, do not try to judge the config — a PHPStan config at all is a stop.**
> Reading it as text cannot be made sound: NEON's inline forms, an `includes: [inner.neon]` whose
> target a line-based collector never reaches, and `\uXXXX` escapes that reconstruct `.php` from
> text containing no `.php` each defeat it. Proving a config harmless needs a real NEON parser
> over the whole include graph, and the only one at hand is inside PHPStan — which starting
> would already run the code in question. So the gate in `references/php-quality.md` §0 stops on
> any config, and its text scan only records **why**; a project with no PHPStan config has no
> config-driven execution path and still gets analysed.
>
> **The read-only cache question is separate and is not judged at all — it is moved.** The gate
> writes an override config outside the workspace that `includes:` the project's own config and
> redirects `tmpDir` and `resultCachePath` into a temp directory. Every project setting still
> applies, and no spelling of an in-repository cache path can put a file in the repository —
> there is nothing to parse and nothing to get wrong.
>
> On your own or your team's branch neither gate fires: without `UNTRUSTED_DIFF` the execution
> gate is inert, and outside read-only mode PHPStan runs with the project's own config exactly
> as before.
>
> **Both gates are driven by exported values, never by prose.** `READ_ONLY` and `UNTRUSTED_DIFF`
> are read by the tool blocks; a prompt that only *says* the review is read-only leaves them at
> `0` and both gates inert. Set them before running any block:
>
> - **Dispatched by `branch-merge-review`** — the values arrive in the prompt's TRUST AND WRITE
>   STATE section. Export them as given. If a placeholder is unsubstituted, report the dispatch
>   as incomplete instead of guessing.
> - **Invoked directly on the user's own checkout** — `UNTRUSTED_DIFF=0`, because the working
>   tree is the user's own. `READ_ONLY=1` whenever the user asked for no writes, otherwise `0`
>   so PHPStan keeps its result cache.
> - **Invoked directly on someone else's branch** — `UNTRUSTED_DIFF=1`. Provenance you cannot
>   vouch for is the case the gate exists for.
>
> Every run prints `static analysis mode: read-only=… untrusted=…` before the analysis, so a
> caller that forgot is visible in the report rather than silently unprotected.
>
> **When the diff is untrusted** — an external contributor's branch, an unfamiliar dependency, any
> code you would not run — the executing tools need isolation before they run. A workspace mounted
> read-only is **not** enough on its own: the `build.rs` reproduced above wrote to an absolute path
> outside the workspace, which a workspace-only restriction does nothing about. The isolation has
> to cover the host: every writable path the process can reach, the network, and the environment
> (`HOME`, `CARGO_HOME`, `CARGO_TARGET_DIR`, `npm_config_cache`, `GOPATH`) pointed into the
> sandbox. Without that, record the check as **`skipped-untrusted-execution`** and say what it
> would have taken to run it.
>
> Reviewing your own team's branch is the ordinary case and needs none of this. But "our repo" is
> not a standing exemption for what the diff *adds*: a newly introduced build hook, plugin, or
> dependency is code that was not there before, and it earns its own look regardless of who wrote
> it. The rule exists so the exception is a decision, not an oversight.


## Reference Files

Load before scanning:
- `references/php-quality.md` — PHP tool setup, execution, and manual patterns
- `references/js-toolchain.md` — JS/TS toolchain and environment-neutral patterns (**single source for tool invocation**)
- `references/js-frontend-quality.md` — browser surface: DOM, jQuery, Svelte, HTMX
- `references/node-quality.md` — server, CLI, daemon, library: async, streams, lifecycle, resources
- `references/python-quality.md` — Python tool setup, execution, and manual patterns
- `references/go-quality.md` — Go tool setup, execution, and manual patterns
- `references/rust-quality.md` — Rust tool setup, execution, and manual patterns
- `references/css-quality.md` — CSS/SCSS tool setup, execution, and manual patterns

Load all applicable files for full-stack review.

**If no reference exists for a detected language, report that language as unsupported and skip
its files — do not stop the whole review.** A mixed repository still gets a full PHP review when
its Kotlin service has no reference yet; what must never happen is substituting another
language's rules, because a PHP checklist applied to Kotlin produces confident findings about
code it does not understand. Name the unreviewed paths in the report so the gap is visible.

### What a language reference must contain

This is the **target contract** for new and restructured references. The five that predate it do not match it yet — their current numbering is below. Restructuring them is
scheduled work, not a precondition for using this table.

| Reference | Current sections |
|---|---|
| `php-quality.md` | §0 version resolution · §1 setup · §2 execution · §3–6 manual patterns |
| `js-toolchain.md` | §1 setup · §2 execution · §3–5 neutral patterns |
| `js-frontend-quality.md` | §1 browser performance · §2 browser style/duplication · §3 Svelte lifecycle |
| `node-quality.md` | §1–7 server-side patterns |
| `python-quality.md` | §0–6 — the first reference that matches the target contract below |
| `go-quality.md` | §0–6 — matches the target contract below |
| `rust-quality.md` | §0–6 — matches the target contract below |
| `css-quality.md` | §1 setup · §2 execution · §3–6 manual patterns |

The target: every `references/{language}-quality.md` carries the same seven sections so this
skill can drive it without knowing the language — the body below never needs editing for a new
language.

**That does not make it a one-file change.** Registering a language for *this* skill takes three
edits (the reference file, its row in the list above, a detection row in Step 1, and an execution
section in Step 2); registering it for the whole review system takes more, and
`branch-merge-review` states the full list. Missing one fails silently: the reference exists and
nothing loads it.

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
| `skipped-untrusted-execution` | The tool would run code from the diff and no isolation was available |
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
- Python: `pyproject.toml`, `setup.py`, `requirements*.txt`, `*.py` → load `references/python-quality.md`
- Go: `go.mod`, `*.go` → load `references/go-quality.md`
- Rust: `Cargo.toml`, `*.rs` → load `references/rust-quality.md`
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

### Python stack

`references/python-quality.md` §4 owns ruff, mypy/pyright, vulture, and radon invocation,
including the cache-suppression flags each one needs to stay read-only safe. Follow its §1 for
version resolution.

### Go stack

`references/go-quality.md` §4 owns `go vet`, staticcheck, golangci-lint, and `gofmt` invocation —
including the `-o /dev/null` form that keeps `go build` from leaving a binary behind.

### Rust stack

`references/rust-quality.md` §4 owns clippy, `cargo check`, and rustfmt invocation, including the
`CARGO_TARGET_DIR` and `--locked` pair that keeps cargo from creating `target/` and `Cargo.lock`.

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
