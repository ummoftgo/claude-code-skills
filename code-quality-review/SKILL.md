---
name: code-quality-review
description: "Review code for quality and performance issues. Trigger when user asks for code quality review, refactoring advice, or code cleanup. Covers: (1) unnecessary or misleading comments, (2) style inconsistencies vs project conventions, (3) duplicated/redundant code, (4) performance inefficiencies — especially evaluation order (cheap checks before expensive ones). Runs CLI tools automatically (PHPStan/phpcs/phpmd/phpcpd for PHP; ESLint/Biome/svelte-check/knip for JS; Stylelint for CSS/SCSS). Adapts per detected language and framework."
---

# Code Quality Review

Runs CLI analysis tools first, then supplements with pattern-based review. Adapts to the detected stack.

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

Run all applicable tools. For each tool, check if it exists first — if not, install per the reference file instructions. Capture output for integration into the report.

### PHP stack

**Before running any PHP tool**, resolve the PHP binary version per `references/php-quality.md` Section 0:
1. Extract required version from `composer.json` (`require.php`)
2. Compare with `php --version`
3. If mismatch → try `php{major}.{minor}` CLI (e.g. `php8.3`); if not found → ask the user
4. Set `PHP_CMD` accordingly; use it for PHPStan (version-sensitive); other tools use default `php`

```bash
# Static analysis — run under resolved PHP_CMD
# phpstan.neon / phpstan.neon.dist 존재 시 --level 생략 (프로젝트 설정 우선)
[ -f phpstan.neon ] || [ -f phpstan.neon.dist ] \
  && $PHP_CMD $(command -v phpstan) analyse <src-dir> --no-progress --error-format=raw \
  || $PHP_CMD $(command -v phpstan) analyse <src-dir> --level=5 --no-progress --error-format=raw

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

## Step 4: Produce Report

Merge tool output and manual findings into `code_quality_report.md`.

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

Fix one finding at a time: Performance → Duplication → CSS → Style → Comments.
Keep each fix minimal. Run tests after each change.
