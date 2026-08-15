# Go Quality Reference

Tooling and manual patterns for Go — an HTTP service, a CLI, a daemon, or a library. Security
rules live in `web-security-review/references/go-security.md`; this file is about correctness,
clarity, and cost.

> **The read-only rule in `SKILL.md` overrides every instruction in this file.** Under a
> read-only request, no command here may install a tool, create a config file, write a
> report file, or auto-fix code — regardless of what an individual section says. Each
> write-causing command below carries its own read-only contract line; when one is
> skipped, record it in the report with its reason.

## Table of Contents
0. [Applicability and Scope](#0-applicability-and-scope)
1. [Version Resolution](#1-version-resolution)
2. [Tool Roles](#2-tool-roles)
3. [Availability and Authority](#3-availability-and-authority)
4. [Execution](#4-execution)
5. [Manual Patterns](#5-manual-patterns)
6. [Severity Mapping](#6-severity-mapping)

---

## 0. Applicability and Scope

| Signal | Meaning |
|---|---|
| `go.mod` | the module root — the unit of version resolution and tool invocation |
| `go.sum` | the verified dependency set; a change here is review scope, not noise |
| `go.work` | a workspace over several modules; each still resolves its own dependencies |
| `*.go` with no `go.mod` | pre-modules or a stray file — tools need a module to run properly |

**The module root is the directory holding `go.mod`**, not the repository root. A repository with
`services/api/go.mod` and `cmd/tool/go.mod` has two roots; run the tools once per root.

**Exclude from review**: `vendor/`, generated files (`*.pb.go`, `*_generated.go`, anything whose
first line matches `^// Code generated .* DO NOT EDIT\.$`), and `testdata/`. Go marks generated
files with that exact line by convention — use it rather than guessing from the name.

## 1. Version Resolution

**Collect all three; they answer different questions.**

| Question | Source |
|---|---|
| What is the **floor**? | `go.mod` → the `go` directive |
| What actually **runs**? | `go.mod` → `toolchain`, `.go-version`, `.tool-versions`, or `go version` |
| What is **tested**? | the CI workflow's Go version matrix |

A gap matters here more than in most languages, because §5's loop-variable rule turns on and off
at 1.22: a module declaring `go 1.21` that CI builds with 1.23 still compiles under the old
semantics, so the finding is real even though the toolchain is new.

The `go` directive changes what is legal. Generics need 1.18; `min`/`max`/`clear` builtins need
1.21; range-over-function iterators need 1.23; and **loop variable semantics changed in 1.22** —
which turns one of the most common Go review findings on and off (see §5). State the directive
you worked from.

## 2. Tool Roles

| Role | Tool | Notes |
|---|---|---|
| Correctness (vet) | **`go vet`** | ships with the toolchain — always available, no install |
| Static analysis | **staticcheck** | the `SA*` checks are the high-value ones |
| Aggregate lint | **golangci-lint** | runs many linters at once; use the project's `.golangci.yml` |
| Formatting | **`gofmt`** / **`goimports`** | `gofmt -l` lists drift without changing anything |
| Vulnerabilities | **govulncheck** | see `go-security.md`; listed here because it is part of the same run |

**Project configuration wins.** If `.golangci.yml` disables a linter, do not report what it
disabled — the project made that call. Read it before running.

`go vet` needs no install and catches real defects (printf arg mismatches, lost struct tags,
unreachable code). Run it even when nothing else is available.

## 3. Availability and Authority

```bash
command -v go gofmt staticcheck golangci-lint
ls "$(go env GOPATH)/bin" 2>/dev/null
```

```powershell
Get-Command go, gofmt, staticcheck, golangci-lint -ErrorAction SilentlyContinue
```

**Read-only:** skip every command in this block; record them as `skipped-read-only`.

```bash
# Normal mode only — `go install` writes a binary into GOPATH/bin
go install honnef.co/go/tools/cmd/staticcheck@latest
go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest
```

## 4. Execution

**`go build` can write a binary into the current directory — it depends on how many packages the
pattern matches.** Measured on go1.22.2: with a single `main` package, `go build ./...` leaves an
executable named after the directory behind; with several packages it discards the results and
writes nothing. Since a review does not know which case it is in before running, always discard
the output explicitly (`-o /dev/null` is accepted in both cases, including multi-package
patterns):

```bash
# Type-checks and compiles without producing an artefact
go build -o /dev/null ./...

# The linters. Neither writes to the working tree.
go vet ./...
staticcheck ./...
golangci-lint run
```

```bash
# Formatting drift — lists files, changes nothing
gofmt -l .
```

**Read-only:** skip this command; record it as `skipped-read-only`.

```bash
# Rewrites source
gofmt -w .
```

**Dependency resolution never mutates the module under a plain build.** Since Go 1.16 the default
is `-mod=readonly`: a missing dependency makes `go vet` fail with `no required module provides
package …; to add it: go get …` rather than editing `go.mod`. Verified on go1.22.2 — do not add
`-mod=mod` to make a command "work", and treat any instruction to run `go get` or `go mod tidy`
during a review as a write.

**When a tool fails with `error obtaining VCS status: exit status 128`**, the build tried to stamp
VCS metadata and the `git` call failed — an unrelated `.git` above the module, or a checkout whose
ownership git distrusts. It is an environment fault, not a code finding: re-run with
`GOFLAGS=-buildvcs=false`, and if it still fails record `execution-error`.

### Interpreting exit codes

| Tool | `0` | non-zero |
|---|---|---|
| `go vet` | clean | `1` — **both** findings and a package that failed to load |
| staticcheck | clean | `1` findings |
| golangci-lint | clean | `1` findings, `3` bad configuration |
| `gofmt -l` | always `0` — **read the output, not the code**; a non-empty list is the finding |
| govulncheck | nothing reachable | `3` a reachable vulnerability, `1` a run error |

Two traps, both measured on go1.22.2:

- `gofmt -l` exits `0` whether or not files are unformatted. A run recorded as `passed` on the
  exit code alone reports nothing.
- `go vet` returns `1` for a compile failure exactly as it does for findings. Read the output:
  text about a package failing to load is `execution-error`, and the vet checks never ran.

## 5. Manual Patterns

### Errors ignored or discarded

```go
// BAD — the blank identifier is a decision, and here it is the wrong one
f, _ := os.Open(path)
defer f.Close()          // nil pointer dereference when Open failed

// GOOD
f, err := os.Open(path)
if err != nil {
    return fmt.Errorf("open %s: %w", path, err)
}
defer f.Close()
```

`errcheck` (inside golangci-lint) catches the mechanical cases. Judge the ones it flags: an
ignored `Close()` on a read-only file is defensible, an ignored `Close()` on a file being written
is data loss.

Also flag error wrapping that loses the chain — `fmt.Errorf("...: %v", err)` where `%w` was meant,
because `errors.Is` and `errors.As` stop working across it.

### Loop variable capture — version-dependent

```go
// Before Go 1.22 this is a real bug: every goroutine sees the final value
for _, item := range items {
    go func() { process(item) }()
}
```

**Go 1.22 changed the semantics**: `for` loop variables are now per-iteration, so the code above
is correct in a module whose `go` directive is 1.22 or later, and broken below it. Read the
directive before reporting — this is a finding that a version check turns off entirely.

### defer inside a loop

```go
// BAD — nothing is released until the function returns; a long loop exhausts handles
for _, path := range paths {
    f, _ := os.Open(path)
    defer f.Close()
}

// GOOD — a function scope per iteration
for _, path := range paths {
    func() {
        f, err := os.Open(path)
        if err != nil { return }
        defer f.Close()
        ...
    }()
}
```

### Slice aliasing after append

```go
// BAD — append may reuse the backing array, so `head` and `all` can share storage
head := all[:2]
head = append(head, x)      // may overwrite all[2]

// GOOD — copy when the two must not alias
head := append([]T(nil), all[:2]...)
```

The same shape hides in a function that stores a slice it received: the caller can still mutate
the backing array. Say so when the value is retained past the call.

### Unbounded goroutines and missing cancellation

```go
// BAD — one goroutine per item, no bound, no way to stop them
for _, item := range items {
    go process(item)
}
```

Flag: a goroutine started without a way to observe its completion (no `WaitGroup`, no channel),
a `context.Context` accepted but never passed down or checked, and an HTTP client or database
call with no timeout. `context.Background()` in a request path is usually a dropped deadline.

### String building in a loop

```go
// BAD — quadratic; each += allocates and copies
var s string
for _, part := range parts { s += part }

// GOOD
var b strings.Builder
for _, part := range parts { b.WriteString(part) }
```

### Queries and I/O inside loops

The N+1 shape is the same as everywhere else — one round trip per item where one query would do.
In Go it usually appears with `rows.Next()` wrapping another query, or a per-item `http.Get`.

### Comments

Same rule as every other language here: delete comments that restate the code, keep the ones that
explain a non-obvious *why*. Go adds one convention worth enforcing — an exported identifier's doc
comment starts with its name, and a doc comment that names a different function is a leftover from
a rename.

## 6. Severity Mapping

| Finding | Severity |
|---|---|
| Ignored error that leads to a nil dereference or silent data loss | High |
| `defer` in a loop over unbounded input | High |
| Unbounded goroutines, or a context accepted and never honoured | High |
| Missing timeout on an outbound HTTP or database call | High |
| Slice aliasing that lets a caller mutate retained state | Medium–High |
| Loop variable capture **below** Go 1.22 | High; **not a finding** at 1.22+ |
| Quadratic string building on unbounded input | Medium–High by input size |
| N+1 queries on a request path | High |
| `%v` where `%w` was meant | Medium — it breaks `errors.Is` for every caller |
| staticcheck `SA*` | Medium unless the specific check says otherwise |
| Formatting drift (`gofmt -l` non-empty) | Low |

Severity follows impact. `go vet` and staticcheck do not rank by cost, so re-rate what they
report rather than passing their labels through.

**An application and a published library carry different impact.** The same defect is rated by
who pays for it: in an application the blast radius ends at this deployment, while in a library
it reaches every consumer and cannot be rolled back by the author alone. Raise a severity one
step when the finding is in a **published library's public API or its documented behaviour** —
a panic reachable from a public function, an API shape that forces every caller to allocate, a
contract the docs promise and the code no longer honours. Lower nothing on that basis: an
application defect is not less real, it is only narrower.


**Run states** — `passed`, `findings`, `skipped-read-only`, `skipped-not-installed`,
`unavailable`, `timeout`, `execution-error`, as defined in `SKILL.md`. A VCS-stamping failure is
`execution-error`, never `passed`.
