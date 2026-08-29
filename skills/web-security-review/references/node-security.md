# Node.js Security Reference

**Language axis.** These are properties of the Node runtime and its package ecosystem — they
hold whether the process serves HTTP, runs as a CLI, or ships as a library. Pair this file with
the **surface axis** reference for what the process actually exposes:
`http-server-security.md`, `browser-security.md`, `native-security.md`. Load every surface that
applies; a package that serves HTTP *and* installs a CLI needs both.

**Severity if violated** is stated per section. As in `php-backend-security.md`, the same `MUST`
grammar carries different severities — the impact decides, not the wording.

## Table of Contents
1. [Command Execution](#1-command-execution)
2. [Path Handling](#2-path-handling)
3. [Deserialization & Dynamic Evaluation](#3-deserialization--dynamic-evaluation)
4. [Prototype Pollution](#4-prototype-pollution)
5. [Dependency & Supply Chain](#5-dependency--supply-chain)
6. [Secrets & Configuration](#6-secrets--configuration)
7. [Deprecated & Bypass APIs](#7-deprecated--bypass-apis)

---

## 1. Command Execution

**Severity if violated**: Critical

### MUST
- MUST NOT pass user input into `exec`, `execSync`, or any call with `shell: true`.
- MUST use `execFile`/`spawn` with an **argument array**, never a concatenated string.
- MUST validate the executable against an allowlist when the program name itself is dynamic.

### Secure pattern

```js
// BAD — a shell parses this; `; rm -rf /` in the filename is a command
exec(`convert ${userFile} out.png`);

// BETTER — no shell, arguments stay arguments
execFile('convert', [userFile, 'out.png'], { shell: false });

// GOOD — also stops the target program reading the value as an option
execFile('convert', ['--', userFile, 'out.png'], { shell: false });
```

**An argument array is not the end of the check.** It stops the *shell* from parsing the value;
it does not stop the *target program*. A `userFile` beginning with `-` is read as an option —
`convert -write /etc/x` is a write, not a filename. Where the program supports `--`, put it
before user values; where it does not, validate against what that specific program accepts.

### The `shell: false` trap on Windows — check the runtime version first

`shell: true` is the obvious hazard, but historically it was **not the only one**.
CVE-2024-27980 ("BatBadBut") was command injection through `spawn`'s *args* on Windows **without**
the shell option, because a `.bat`/`.cmd` target is run through `cmd.exe`. CVE-2024-36138 followed
as an incomplete-fix for the same class.

**Both are patched.** The follow-up fix shipped in **18.20.4, 20.15.1, and 22.4.1**; current Node
treats `.bat`/`.cmd` as not directly executable, so `execFile` refuses them without
`shell: true`. Establish the project's runtime first: at or above those versions this is not a
finding, below them it is Critical.

What still holds on any version: check the whole path from input to argument — where the value
comes from, whether it is constrained, and whether the target resolves to a batch file. Pin the
executable to an absolute path rather than letting `PATH` decide.

### Audit grep patterns

```bash
rg -n "exec\(|execSync\(|shell:\s*true" --glob "*.{js,mjs,cjs,ts,mts,cts,tsx}" .
rg -n "spawn(Sync)?\(" -A3 --glob "*.{js,mjs,cjs,ts,mts,cts,tsx}" .
```

## 2. Path Handling

**Severity if violated**: Critical

### MUST
- MUST resolve user-supplied paths and verify the result stays inside the intended root.
- MUST NOT rely on stripping `../` — normalisation before the check is what makes it sound.
- MUST reject absolute paths and, on Windows, drive-relative forms (`C:file`) when a relative
  path was expected.

### Secure pattern

```js
// BAD — stripping `..` is not normalisation; `....//` survives it
const target = path.join(ROOT, req.query.file.replace(/\.\./g, ''));

// GOOD — canonicalise BOTH sides once, then compare canonical against canonical
const rootReal = await fs.promises.realpath(ROOT);          // resolve the root itself, once
const target = path.resolve(rootReal, req.query.file);
if (target !== rootReal && !target.startsWith(rootReal + path.sep)) {
  throw new Error('outside root');                          // cheap lexical reject first
}
const real = await fs.promises.realpath(target);            // throws if absent — handle
if (real !== rootReal && !real.startsWith(rootReal + path.sep)) {
  throw new Error('escapes via link');
}
```

Three things this shape gets right:

- `!== root && !startsWith(root + sep)` — a bare `startsWith(root)` also accepts `/srv/app-backup`
  when the root is `/srv/app`.
- `resolve` + `startsWith` is **lexical only**. It cannot see a symlink or a Windows junction
  inside the root that points out of it; `realpath` is what closes that, and a repository under
  analysis can contain exactly such a link.
- **Both sides are canonicalised.** Comparing a `realpath`-ed target against the raw `ROOT`
  string rejects legitimate paths whenever the root itself is a link. Measured on Node v24.18.0
  with `ROOT = '/bin'`: `/bin/sh` resolves to `/usr/bin/dash`, which does not start with `/bin`,
  so the one-sided check throws on a file that is plainly inside the root. Resolving `ROOT` first
  makes the same case pass and keeps the escape case rejected.

Note that `path` does **not** URL-decode. `%2f` in a query value stays literal here — decode
once at the HTTP boundary and validate after decoding (see `http-server-security.md` §5).

## 3. Deserialization & Dynamic Evaluation

**Severity if violated**: Critical

### MUST
- MUST NOT pass untrusted input to `eval`, `new Function`, or `vm.runInThisContext`.
- MUST NOT use a deserializer that reconstructs arbitrary types from untrusted data
  (`node-serialize`, `funcster`, and similar). `JSON.parse` is the safe default.
- MUST treat `vm` as an **isolation convenience, not a security boundary** — Node's own docs say
  it is not a sandbox, and escapes are well known.

### Audit grep patterns

```bash
rg -n "\beval\(|new Function\(|vm\.(runIn|createContext)" --glob "*.{js,mjs,cjs,ts,mts,cts}" .
rg -n "node-serialize|funcster|unserialize\(" --glob "*.{js,mjs,cjs,ts,json}" .
```

## 4. Prototype Pollution

**Severity if violated**: High

A merge or path-assign helper that walks attacker-controlled keys can write `__proto__`,
`constructor`, or `prototype` and change objects the code never touched. The damage shows up far
from the assignment, which is why it survives review.

### MUST
- MUST reject `__proto__`, `constructor`, and `prototype` as keys when assigning from parsed input.
- MUST use `Object.create(null)` or a `Map` for lookup tables built from user data.
- MUST NOT deep-merge request bodies into configuration or option objects.

```js
// BAD — one request body can set Object.prototype.isAdmin
deepMerge(defaults, req.body);

// GOOD — explicit fields only
const options = { limit: toInt(req.body.limit), sort: allowSort(req.body.sort) };
```

## 5. Dependency & Supply Chain

**Severity if violated**: High

### MUST
- MUST commit a lockfile and install with `npm ci` (or the equivalent) in CI, so the resolved
  tree is the reviewed tree.
- MUST review newly added or major-bumped dependencies in the diff — a lockfile change is part
  of the security scope, not noise.
- MUST treat install-time lifecycle scripts in a **new** dependency as a finding until read;
  they run with full user permissions.
- MUST NOT commit `.npmrc` containing a token.

### Audit

```bash
# Known advisories. `--omit=dev` narrows the audit to production dependencies — use it to
# prioritise, not to conclude, since a dev dependency still runs on the developer's machine
# and in CI.
npm audit                 # everything
npm audit --omit=dev      # production only

# A. Installed dependencies. A registry dependency runs `preinstall`, `install`, and
# `postinstall`; a dependency installed from git or a local path also runs `prepare`.
# Glob the **whole** tree — `node_modules/*/package.json` misses `@scope/pkg` and anything
# nested, and a head limit hides the rest of the list rather than reporting the truncation.
rg -n --glob 'node_modules/**/package.json' \
  '"(preinstall|install|postinstall|prepare)"\s*:'

# B. The repository's own package(s). `npm install` in this checkout runs the root and
# workspace scripts, which is a wider set — the publish-side `prepublish`/`prepublishOnly`
# and `preprepare`/`postprepare` hooks live here, not in an installed registry dependency.
rg -n --glob '!node_modules' --glob 'package.json' \
  '"(preinstall|install|postinstall|prepare|preprepare|postprepare|prepublish|prepublishOnly)"\s*:'
```

Keep the two lists apart in the report. "A dependency ships a `postinstall`" and "this repository
gained a `prepare` script" are different findings with different owners.

**Read-only:** skip this command; record it as `skipped-read-only`.

```bash
# `npm audit fix` rewrites the lockfile — a review must not
npm audit fix
```

## 6. Secrets & Configuration

**Severity if violated**: High

### MUST
- MUST read secrets from the environment or a secret manager, never from source.
- MUST NOT log `process.env` wholesale, request headers, or error objects that carry
  `Authorization`.
- MUST NOT ship `.env` files in the published package — check `files`/`.npmignore`.
- MUST fail closed when a required secret is missing, rather than falling back to a default.

```bash
rg -n "process\.env" --glob "*.{js,mjs,cjs,ts}" -A1 . | rg -i "log|console|print"
rg -n "api[_-]?key|secret|token|password" --glob "*.{js,mjs,cjs,ts}" -i . | rg -v "process\.env"
```

## 7. Deprecated & Bypass APIs

**Severity if violated**: Medium–High depending on context

- `process.binding()` — a deprecated internal API. It was usable to bypass the permission model
  through path traversal; current Node blocks it when the permission model is enabled. Report its
  presence as a finding on its own merits (unsupported internal surface), and check the runtime
  version before claiming the bypass specifically.
- `require()` built from a runtime string — the module actually loaded is not reviewable.
- `Buffer(size)` (the old constructor) — deprecated, but **not** because it leaks memory: it has
  been zero-filled since Node 8 (verified on v24: `Buffer(32)` is all zeros). The real hazards
  are type confusion — `Buffer(userValue)` allocates when the value is a number and copies when
  it is a string, so one input type change turns a copy into a huge allocation — and the
  denial-of-service that follows. Use `Buffer.alloc` / `Buffer.from` with an explicit type check.
  `Buffer.allocUnsafe` is the one that returns uninitialised memory; it needs its own
  justification.

Node's permission model is `--permission` with `--allow-fs-read` and friends (stable since
22.13 / 23.5; earlier versions used `--experimental-permission`). It is a useful defence when
the process handles untrusted input. **Its absence is not a finding** — recommend it where it
fits, do not report it as a vulnerability.
