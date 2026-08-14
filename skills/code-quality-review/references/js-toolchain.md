# JavaScript / TypeScript Shared Reference

The toolchain and the language-level patterns that apply wherever JS/TS runs — a browser
bundle, a Node server, a CLI, a library. Environment-specific review lives in
`js-frontend-quality.md` (DOM, jQuery, Svelte, HTMX) and `node-quality.md` (server, CLI,
daemon, library).

**This file is the single source for tool invocation.** When a tool command drifts between
files, the reader cannot tell which one is authoritative — so the frontend and Node references
point here rather than repeating commands.

> **The read-only rule in `SKILL.md` overrides every instruction in this file.** Under a
> read-only request, no command here may install a tool, create a config file, write a
> report file, or auto-fix code — regardless of what an individual section says. Each
> write-causing command below carries its own read-only contract line; when one is
> skipped, record it in the report with its reason.

## Table of Contents
1. [CLI Tool Setup](#1-cli-tool-setup)
2. [Running the Tools](#2-running-the-tools) — ESLint · Biome · Oxlint · TypeScript · svelte-check · knip
3. [Comment Quality](#3-comment-quality)
4. [Style Conventions](#4-style-conventions)
5. [Duplication](#5-duplication)

---

## 1. CLI Tool Setup

Tools are project-local (npm). Install only what is missing.

**Read-only:** skip every command in this block; record them as `skipped-read-only`.

```bash
# ESLint — use if eslint.config.js / .eslintrc.* exists in project
if [ ! -f node_modules/.bin/eslint ]; then
  npm install --save-dev eslint
fi

# Biome — use if biome.json exists (replaces ESLint + Prettier)
if [ ! -f node_modules/.bin/biome ]; then
  npm install --save-dev --save-exact @biomejs/biome
  # First time: npx --no @biomejs/biome init
fi

# Oxlint — use for large codebases or alongside ESLint for speed
if [ ! -f node_modules/.bin/oxlint ]; then
  npm install --save-dev oxlint
fi

# svelte-check — install if .svelte files exist
if ls src/**/*.svelte &>/dev/null 2>&1 || ls *.svelte &>/dev/null 2>&1; then
  if [ ! -f node_modules/.bin/svelte-check ]; then
    npm install --save-dev svelte-check
  fi
fi

# knip — unused exports, files, dependencies
if [ ! -f node_modules/.bin/knip ]; then
  npm install --save-dev knip
fi
```

**Tool selection priority**:
1. If `biome.json` exists → use Biome (`check` covers lint + format)
2. Else if `eslint.config.*` or `.eslintrc.*` exists → use ESLint
3. Else → install ESLint (most compatible default)

---

## 2. Running the Tools

### ESLint
```bash
# Report only (no auto-fix)
npx --no eslint . --format=compact

# With specific directories
npx --no eslint src/ --format=compact --max-warnings=0

# JSON output for scripting
# **Read-only:** skip this command; record it as `skipped-read-only`.
npx --no eslint . --format=json -o eslint-report.json

# Auto-fix safe issues
# **Read-only:** skip this command; record it as `skipped-read-only`.
npx --no eslint . --fix
```

### Biome
```bash
# Lint + format check combined
npx --no @biomejs/biome check .

# CI mode (stricter — fails on warnings too)
npx --no @biomejs/biome ci .

# Auto-fix
# **Read-only:** skip this command; record it as `skipped-read-only`.
npx --no @biomejs/biome check --write .
```

### Oxlint
```bash
# Fast lint pass (good for large codebases)
npx --no oxlint .

# With TypeScript support
npx --no oxlint --tsconfig tsconfig.json .

# Auto-fix
# **Read-only:** skip this command; record it as `skipped-read-only`.
npx --no oxlint --fix .
```

### TypeScript — `tsc --noEmit`

Type checking is a quality tool, not a build step. Read `tsconfig.json` first: findings differ
sharply by strictness, and a strictness gap explains a whole class of runtime errors better than
any individual line (see `node-quality.md` §6).

**Read `tsconfig.json` before running.** `--noEmit` suppresses `.js` and `.d.ts` output, but it
does **not** make the run write-free: with `incremental: true` or `composite: true`, `tsc` still
writes a `.tsbuildinfo` file. Treating `--noEmit` as read-only safe on such a project puts a new
file in the user's repository during a review that promised not to.

```bash
# Neither incremental nor composite → --noEmit writes nothing
npx --no tsc --noEmit

# A specific project file in a monorepo
npx --no tsc --noEmit --project packages/api/tsconfig.json
```

```bash
# incremental: true → turn the build-info write off explicitly. This is the read-only-safe
# form: it writes nothing, so it runs under a read-only request like any other check.
npx --no tsc --noEmit --incremental false
```

`composite: true` is the one case with no safe form — the project requires emit, and the
build-info write cannot simply be turned off. Under a read-only request do not improvise a
redirect: record type checking as `skipped-read-only` and say it needs write permission or a
non-composite project reference.

So the rule is three-way, not two: **no incremental/composite** → run plain `--noEmit`;
**incremental** → run `--incremental false`; **composite** → skip and report.

### svelte-check
```bash
# Machine-readable output
npx --no svelte-check --output machine

# Verbose (includes warnings)
npx --no svelte-check --output machine-verbose

# Check specific directory
npx --no svelte-check --workspace src/
```

### knip — unused code & dependencies
```bash
# Full report: unused files, exports, dependencies
npx --no knip

# Fix automatically where possible
# **Read-only:** skip this command; record it as `skipped-read-only`.
npx --no knip --fix

# Specific category
npx --no knip --include files          # only unused files
npx --no knip --include dependencies   # only unused npm packages
npx --no knip --include exports        # only unused exports
```

---

## 3. Comment Quality

### Flag
```js
// BAD — restates code
const total = items.length; // get the total

// BAD — stale JSDoc (param type wrong)
/**
 * @param {String} id   ← should be number
 */
function getUser(id) { ... }

// BAD — commented-out dead code
// const oldApi = fetch('/api/v1/users');
const data = await fetch('/api/v2/users');
```

### Keep
```js
// GOOD — explains non-obvious behaviour
// Debounce 300ms: avoids search API call on every keystroke
const debouncedSearch = debounce(search, 300);

// GOOD — intentional workaround with reason
// Safari < 16 lacks :has() support; toggling class manually instead
```

---

## 4. Style Conventions

Detect project majority first (ESLint/Biome handle most of this). Flag manually:

```js
// BAD — var in an ES6+ project
var count = 0;

// BAD — .then() mixed into async/await function
async function loadUser() {
    const res = await fetch('/api/user');
    return res.json().then(u => u);   // ← inconsistent
}

// BAD — mixed quote style in same file
const a = 'hello';
const b = "world";
```

---

## 5. Duplication

knip covers unused exports. Also flag manually:

```js
// BAD — same fetch + error handling in 5 files
const res = await fetch('/api/users');
if (!res.ok) throw new Error('Failed');
const data = await res.json();
// → extract to api(url, options) helper
```

### Grep patterns
```bash
rg -n "await fetch\(" --glob "*.{js,mjs,cjs,ts,mts,cts,tsx,svelte}" | sort
```

Surface-specific duplication — repeated DOM queries, near-identical jQuery handlers — lives in
`js-frontend-quality.md`. Server-side duplication patterns live in `node-quality.md`.

---

