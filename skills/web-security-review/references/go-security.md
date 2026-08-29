# Go Security Reference

**Language axis.** These are properties of the Go runtime and its module ecosystem — they hold
whether the binary serves HTTP, runs as a CLI, or ships as a library. Pair this file with the
**surface axis** reference for what the process actually exposes: `http-server-security.md`,
`browser-security.md`, `native-security.md`. Load every surface that applies.

**Severity if violated** is stated per section. As in `php-backend-security.md`, the same `MUST`
grammar carries different severities — the impact decides, not the wording.

## Table of Contents
1. [Command Execution](#1-command-execution)
2. [Path Handling](#2-path-handling)
3. [SQL and Query Construction](#3-sql-and-query-construction)
4. [Template Rendering](#4-template-rendering)
5. [Concurrency as a Security Property](#5-concurrency-as-a-security-property)
6. [Dependency & Supply Chain](#6-dependency--supply-chain)
7. [Secrets & Configuration](#7-secrets--configuration)
8. [Cryptography and Randomness](#8-cryptography-and-randomness)
9. [Integer and Slice Boundaries](#9-integer-and-slice-boundaries)

---

## 1. Command Execution

**Severity if violated**: Critical

Go has an advantage here worth stating plainly: `exec.Command` takes an argument slice and does
**not** invoke a shell. The injection shape only appears when someone reintroduces one.

### MUST
- MUST NOT build a command by passing `sh -c` or `cmd /c` a string containing user input.
- MUST validate the executable against an allowlist when the program name is dynamic.
- MUST NOT let user input become an option — prepend `--` where the program supports it.

```go
// BAD — a shell is back, and with it the injection
exec.Command("sh", "-c", "convert "+userFile+" out.png")

// GOOD — no shell; arguments stay arguments
exec.Command("convert", "--", userFile, "out.png")
```

`exec.LookPath` resolves through `PATH`. In a privileged process, or one whose environment an
attacker can influence, pin the absolute path instead.

```bash
rg -n 'exec\.Command\("(sh|bash|cmd|powershell)"' --glob "*.go"
rg -n 'exec\.(Command|CommandContext)' -A2 --glob "*.go"
```

## 2. Path Handling

**Severity if violated**: Critical

### MUST
- MUST clean and verify containment before opening a user-supplied path.
- MUST NOT concatenate with `+` or `path.Join` for filesystem paths — `filepath.Join` is the
  OS-aware one, and it cleans, which is what makes the check meaningful.
- MUST resolve symlinks when the tree under review can contain them.

```go
// BAD — Join cleans, but nothing proves the result is inside root
target := filepath.Join(root, r.URL.Query().Get("file"))

// GOOD — canonicalise both sides, then compare
rootReal, err := filepath.EvalSymlinks(root)
if err != nil { return err }
target := filepath.Join(rootReal, userPath)
if target != rootReal && !strings.HasPrefix(target, rootReal+string(os.PathSeparator)) {
    return errors.New("outside root")
}
real, err := filepath.EvalSymlinks(target)      // errors if absent — handle
if err != nil { return err }
if real != rootReal && !strings.HasPrefix(real, rootReal+string(os.PathSeparator)) {
    return errors.New("escapes via link")
}
```

`os.Root` (Go 1.24+) enforces containment in the standard library and is the better answer where
the toolchain allows it — check the `go` directive before recommending it.

Archive extraction is the same defect with a different door: a `tar` or `zip` member named
`../../etc/passwd` writes outside the destination unless every member is validated. Go's standard
library does not validate for you.

## 3. SQL and Query Construction

**Severity if violated**: Critical

### MUST
- MUST use placeholders (`?`, `$1`) for every value. `database/sql` sends them to the driver
  separately — that is the protection.
- MUST NOT build SQL with `fmt.Sprintf`, `+`, or a template where any part is user input.
- MUST allowlist identifiers (table, column, sort direction); a placeholder cannot bind one.

```go
// BAD
db.Query(fmt.Sprintf("SELECT * FROM users WHERE email = '%s'", email))

// GOOD
db.Query("SELECT * FROM users WHERE email = $1", email)
```

In an ORM the escape hatches are what to search: GORM `Raw`/`Exec`/`Where` with a formatted
string, sqlx `Sprintf` into a query, and any `ORDER BY` built from a request value.

```bash
rg -n '(Query|Exec|QueryRow)\w*\(\s*(fmt\.Sprintf|".*"\s*\+)' --glob "*.go"
```

## 4. Template Rendering

**Severity if violated**: High — `text/template` into HTML is an XSS sink, and that is what the
severity should say.

Raise to Critical only when execution is actually reachable. Go templates call **only** what the
data namespace and the `FuncMap` expose, so an attacker-controlled template text is not code
execution by itself — it is XSS plus whatever that namespace happens to reach.

Critical needs a named target. Three places to look, not one:

- a `FuncMap` entry that writes, deletes, sends, or shells out;
- an **exported method** on the data (or on anything reachable from it) that does the same;
- a **function value** stored in a struct field or map entry — the builtin `call` invokes those,
  so `{{ call .Wipe "x" }}` reaches a `Wipe func(string) string` field with no `FuncMap` involved
  (reproduced on go1.22.2).

Name the target in the finding. If you cannot name one, the severity is High

### MUST
- MUST use **`html/template`** for anything rendered into HTML. `text/template` performs no
  contextual escaping, and the two have identical APIs — the import line is the whole difference,
  which is exactly why this defect survives review.
- MUST NOT wrap user data in `template.HTML`, `template.JS`, or `template.URL`; those types mean
  "already safe" and disable escaping for that value.
- MUST NOT build the template text itself from user input.

```go
// BAD — no escaping at all; every value is an XSS sink
import "text/template"

// GOOD — contextual escaping by output position
import "html/template"
```

```bash
rg -n '"text/template"' --glob "*.go"
rg -n 'template\.(HTML|JS|URL|CSS|Srcset)\(' --glob "*.go"
```

When the output reaches a browser, `browser-security.md` applies on top of this section.

## 5. Concurrency as a Security Property

**Severity if violated**: High

Data races in Go are not only a correctness problem — a race on an authorization decision, a
session map, or a token cache is an authentication bypass that appears under load and vanishes
under a debugger.

### MUST
- MUST guard shared mutable state with a mutex or confine it to one goroutine. A plain `map`
  written from several goroutines can also crash the process (`concurrent map writes`), which is
  a denial of service.
- MUST bound concurrency started from request input — one goroutine per request item, unbounded,
  is a resource-exhaustion primitive.
- MUST propagate `context.Context` and honour cancellation, so a disconnected client stops the
  work it started.

```bash
# The race detector is the tool for this. It needs to build and run tests.
GOTOOLCHAIN=local go test -race ./...
```

**Read-only note:** `go test -race` writes to the build cache rather than the working tree, so
the write axis alone would allow it under a read-only review.

**Untrusted-diff rule:** the other axis forbids it. `go test -race` compiles and runs the
project's test binary — the diff's own code, plus anything its `TestMain` or `init` does. For a
diff you would not execute, record it as `skipped-untrusted-execution` rather than running it.
Under a read-only review of your own branch it may run; say in the report that it ran.

`GOTOOLCHAIN=local` is not optional. Without it the `toolchain` line in `go.mod` — a file the
diff controls — makes the `go` command download and execute a different toolchain before it
reaches your code, which is a code-execution path that the race detector's own gating never
sees.

## 6. Dependency & Supply Chain

**Severity if violated**: High

### MUST
- MUST commit `go.sum` and treat a change to it as review scope — it is the integrity record.
- MUST review newly added or major-bumped modules in the diff.
- MUST NOT add a `replace` directive pointing outside the repository in a release build; it
  silently substitutes code the module proxy never verified.

Go's design removes two ecosystem risks that other languages carry, and the review should say so
rather than looking for them: **modules have no install-time hook** — nothing equivalent to an npm
`postinstall` or a Python `setup.py` runs on `go get` — and the checksum database plus `go.sum`
make a silent content change to a published version detectable.

What remains is typosquatting, a compromised release of a real module, and `replace` misuse.

```bash
# Reachable vulnerabilities — symbol-level, so it reports what the code actually calls.
# Exit 3 means a reachable vulnerability was found; 1 means the run failed.
govulncheck ./...

# `replace` directives, and any module served from outside the proxy
rg -n '^\s*replace ' go.mod

# Integrity settings in CI, Dockerfiles, and Makefiles
rg -n 'GOSUMDB\s*=\s*off|GONOSUMDB|GOPRIVATE|GOINSECURE|GOFLAGS.*-mod=mod' --glob '!vendor'
```

Read the match before rating it — these settings are not equivalent:

| Setting | What it means |
|---|---|
| `GOSUMDB=off` | the checksum database is disabled **globally**. High: nothing verifies a module the `go.sum` has not already pinned |
| `GOPRIVATE` / `GONOSUMDB` | the normal way to exempt an *internal* module path from the proxy and sum database. Check that the patterns are specific — a bare `*` is the `GOSUMDB=off` case wearing a different name |
| `GOINSECURE` | allows module fetch over plain HTTP for the listed patterns — **specificity narrows the blast radius, it does not make it safe.** Report it, and say which paths it covers; a narrow pattern is a smaller finding, not a non-finding |
| `GOFLAGS=-mod=mod` | re-enables automatic `go.mod` edits during a build, so the built tree can differ from the reviewed one |

`GONOSUMCHECK` is **not** a Go environment variable — it belonged to the pre-modules `vgo`
prototype. Reporting it as a disabled integrity check is a finding about nothing; verified against
`go env` on go1.22.2, which lists `GOSUMDB`, `GONOSUMDB`, `GOPRIVATE`, and `GOINSECURE`.

## 7. Secrets & Configuration

**Severity if violated**: High

### MUST
- MUST read secrets from the environment or a secret manager, never from source — and remember
  that a Go binary ships its string constants, so a hardcoded key is extractable with `strings`.
- MUST NOT log request structs, `os.Environ()`, or errors that carry credentials.
- MUST fail closed when a required secret is missing.

```go
// BAD — a default that silently downgrades security
key := os.Getenv("SIGNING_KEY")
if key == "" { key = "dev-key" }

// GOOD
key, ok := os.LookupEnv("SIGNING_KEY")
if !ok { return errors.New("SIGNING_KEY is required") }
```

```bash
rg -n '(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*"' --glob "*.go"
```

## 8. Cryptography and Randomness

**Severity if violated**: High

### MUST
- MUST use `crypto/rand` for tokens, session identifiers, and anything unpredictable.
  `math/rand` is deterministic from its seed, so a reset token built with it is guessable.
- MUST compare secrets with `subtle.ConstantTimeCompare`, never `==` or `bytes.Equal`.
- MUST NOT set `InsecureSkipVerify: true` in a `tls.Config` outside a test.
- MUST NOT use `crypto/md5` or `crypto/sha1` for anything security-bearing.

```go
// BAD — predictable
b := make([]byte, 32)
mathrand.Read(b)

// GOOD
b := make([]byte, 32)
if _, err := crypto_rand.Read(b); err != nil { return err }
```

Go 1.20 removed the need to seed `math/rand`, which makes the misuse *look* modern — the output
is still not cryptographically secure. Judge by the import, not by whether it is seeded.

```bash
rg -n 'math/rand|InsecureSkipVerify|crypto/(md5|sha1)' --glob "*.go"
```

## 9. Integer and Slice Boundaries

**Severity if violated**: Medium–High depending on reachability

### MUST
- MUST bound a length or size taken from input before using it to allocate: `make([]byte, n)`
  with an attacker-controlled `n` is a memory-exhaustion primitive.
- MUST check the conversion when narrowing an integer from input (`int64` → `int32`, any signed
  → `uint`); Go wraps silently, and a negative length becomes an enormous unsigned one.
- MUST bound request body size — `http.MaxBytesReader` — before decoding JSON.

```go
// BAD — the client decides the allocation
buf := make([]byte, header.Length)

// GOOD
if header.Length < 0 || header.Length > maxFrame { return errFrameTooLarge }
buf := make([]byte, header.Length)
```

`go vet` does not catch these. They are found by reading the path from input to allocation.
