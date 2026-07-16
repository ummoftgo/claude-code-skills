---
name: code-quality-review
description: "Review code for quality and performance issues. Trigger when user asks for code quality review, refactoring advice, or code cleanup. Covers: (1) unnecessary or misleading comments, (2) style inconsistencies vs project conventions, (3) duplicated/redundant code, (4) performance inefficiencies — especially evaluation order (cheap checks before expensive ones). Runs CLI tools automatically (PHPStan/phpcs/phpmd/phpcpd for PHP; ESLint/Biome/svelte-check/knip for JS; Stylelint for CSS/SCSS). Adapts per detected language and framework."
---

# Code Quality Review

Runs CLI analysis tools first, then supplements with pattern-based review. Adapts to the detected stack.

> **Read-only mode (priority rule).** If the user asked for a review **without changing anything** (e.g. "수정하지 말고 검토만", "read-only", review delegated under a read-only sandbox), then this skill must not write to the workspace:
> - **Do not install** missing tools (no `npm install`, `composer require`, PHAR downloads, etc.). Run only the tools already present; for each missing tool, record it as **`skipped (not installed)`** in the report.
> - **Do not create the report file.** Emit the report **inline** in your response instead of writing to `.tasks/reports/`.
>
> Only perform installs and file writes when the user has not restricted writes. When in doubt, treat the request as read-only and ask before installing or writing.

## Reference Files

Load before scanning:
- `references/php-quality.md` — PHP tool setup, execution, and manual patterns
- `references/js-quality.md` — JS/Svelte/HTMX tool setup, execution, and manual patterns
- `references/css-quality.md` — CSS/SCSS tool setup, execution, and manual patterns

Load all applicable files for full-stack review.

## Step 1: Detect Stack and Infer Conventions

Inspect the project root to determine languages and frameworks:
- PHP: `composer.json`, `*.php` files → load `references/php-quality.md`
- JS/Svelte/HTMX: `package.json`, `*.svelte`, `*.js` → load `references/js-quality.md`
- CSS/SCSS: `*.css`, `*.scss`, `*.sass` files → load `references/css-quality.md`

Infer project conventions from **existing code majority** (not assumed standards):
- Naming style, indentation, quote style, comment format, component structure

## Step 2: Run CLI Tools

Run all applicable tools. For each tool, check if it exists first — if not, install per the reference file instructions **(unless read-only mode applies — then skip the install and mark the tool `skipped (not installed)`)**. Capture output for integration into the report.

### PHP stack

**Before running any PHP tool**, resolve the PHP binary version per `references/php-quality.md` Section 0:
1. Extract required version from `composer.json` (`require.php`)
2. Compare with `php --version`
3. If mismatch → try `php{major}.{minor}` CLI (e.g. `php8.3`); if not found → ask the user
4. Set `PHP_CMD` accordingly; use it for PHPStan (version-sensitive); other tools use default `php`

```bash
# Derive src-dir: read the first PSR-4 *directory value* from composer.json;
# fall back to src/, app/, or project root if autoload not defined.
# PSR-4 maps namespace keys ("App\\") to directory values ("src/") — use array_values, not array_keys.
# Example: SRC_DIR=$(php -r '$p=json_decode(file_get_contents("composer.json"),true)["autoload"]["psr-4"]??[];echo rtrim(array_values($p)[0]??""," /");') || SRC_DIR="src"

# Static analysis — run under resolved PHP_CMD
# If phpstan.neon / phpstan.neon.dist exists, omit --level (project config takes precedence)
# Use if/else to avoid double-execution: phpstan exits non-zero when it finds errors,
# which would trigger the || fallback in a chained &&/|| expression.
if [ -f phpstan.neon ] || [ -f phpstan.neon.dist ]; then
  $PHP_CMD $(command -v phpstan) analyse <src-dir> --no-progress --error-format=raw
else
  $PHP_CMD $(command -v phpstan) analyse <src-dir> --level=5 --no-progress --error-format=raw
fi

# Style/convention (version-agnostic)
phpcs --standard=PSR12 --report=full <src-dir>

# Complexity, duplication, dead code (version-agnostic)
phpmd <src-dir> text cleancode,codesize,naming,unusedcode

# Copy-paste detection (version-agnostic)
phpcpd <src-dir>
```

### JS / Svelte / HTMX stack
```bash
# Linting (use whichever is configured in the project)
npx eslint . --format=compact          # if ESLint config exists
npx @biomejs/biome check .             # if biome.json exists
npx oxlint .                           # if oxlint configured

# Svelte type check (if .svelte files exist)
npx svelte-check --output machine

# Unused exports / dead dependencies
npx knip
```

### CSS / SCSS stack
```bash
# Stylelint (use if .css or .scss files exist)
npx stylelint "**/*.css" "**/*.scss" --formatter=compact
```

See reference files for installation instructions when tools are missing.

## Step 3: Manual Review — Four Categories

After collecting tool output, perform pattern-based review to catch what tools miss.

### Category 1 — Unnecessary Comments
Flag: restate-the-code comments, commented-out dead code, stale TODOs.
Keep: explains "why", intentional workarounds with reason, correct docblocks.

### Category 2 — Style Inconsistencies
Flag deviations from the inferred project majority only — not from external standards.
Tools cover most of this; focus manual review on semantic inconsistencies tools can't detect
(e.g., same concept named differently in different files).

**Svelte lifecycle review rule**: Before flagging any store subscription or lifecycle issue in a `.svelte` file, read the entire component. The `$store` reactive syntax auto-unsubscribes — never flag it as a leak. Only flag manual `.subscribe()` calls that lack an `onDestroy` cleanup. See `references/js-quality.md` Section 7 for the full decision tree.

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

Save the report to: `.tasks/reports/{yyyy-mm-dd}-{hh-mm}-{slug}-quality.md` **(skip this in read-only mode — emit the report inline instead).**

- **Path**: Create `.tasks/reports/` if it does not exist.
- **Date/time**: Current local date and time (e.g., `2026-03-30-14-05`).
- **Slug**: Short identifier in kebab-case derived from the user's request or the target — e.g., feature name, file name, or a keyword from the request. Max ~30 chars.
- **Example**: `.tasks/reports/2026-03-30-14-05-user-auth-quality.md`

Merge tool output and manual findings into this file.

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
