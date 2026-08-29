# Rust Security Reference

**Language axis.** These are properties of the Rust toolchain and the crates.io ecosystem — they
hold whether the binary serves HTTP, runs as a CLI, or ships as a library. Pair this file with the
**surface axis** reference for what the process actually exposes: `http-server-security.md`,
`browser-security.md`, `native-security.md`. Load every surface that applies.

**Severity if violated** is stated per section. As in `php-backend-security.md`, the same `MUST`
grammar carries different severities — the impact decides, not the wording.

**Where the review effort goes.** The compiler already rejects use-after-free, data races between
threads, and most buffer overflows in safe code. Reporting those as risks in safe Rust is noise
that costs the report its credibility. The real surface is: `unsafe`, panics reachable from input,
resource exhaustion, dependencies, and the same injection classes every language has.

## Table of Contents
1. [`unsafe` and Its Invariants](#1-unsafe-and-its-invariants)
2. [Panics as Denial of Service](#2-panics-as-denial-of-service)
3. [Command Execution](#3-command-execution)
4. [Path Handling](#4-path-handling)
5. [SQL and Query Construction](#5-sql-and-query-construction)
6. [Deserialization and Resource Limits](#6-deserialization-and-resource-limits)
7. [Dependency & Supply Chain](#7-dependency--supply-chain)
8. [Secrets & Configuration](#8-secrets--configuration)
9. [Cryptography and Randomness](#9-cryptography-and-randomness)

---

## 1. `unsafe` and Its Invariants

**Severity if violated**: two different findings, rated separately.
**A missing safety comment is Medium** — a documentation defect, whatever the block touches; the
code may well be correct. **A demonstrably violated invariant is Critical** — you can name the
input that makes the block read out of bounds, alias mutably, or build a reference to
uninitialised memory. Do not promote the first into the second because the data came from input;
say which of the two you are reporting.

### MUST
- MUST carry a comment stating the invariant that makes the block sound. An `unsafe` block with
  no such comment is a finding regardless of whether it is correct today — the next editor has
  nothing to preserve.
- MUST NOT construct a slice or reference from a length or pointer that came from input without
  validating it first (`from_raw_parts`, `get_unchecked`, `transmute`).
- MUST NOT use `unsafe` to bypass a borrow error that a redesign would fix; say which invariant
  the compiler could not see.

```rust
// BAD — the length is attacker-controlled and unchecked
let data = unsafe { std::slice::from_raw_parts(ptr, header.len) };

// GOOD — bounded, and every condition the function requires is named
assert!(header.len <= MAX_FRAME);
// SAFETY: `ptr` is non-null and `u8`-aligned; it points into `buf`, a single allocation of at
// least `header.len` initialised bytes; `buf` outlives `data` and is not mutated while it
// lives; `header.len` is bounded by MAX_FRAME, far below `isize::MAX`.
let data = unsafe { std::slice::from_raw_parts(ptr, header.len) };
```

`from_raw_parts` requires **all** of: non-null, correctly aligned, one contiguous allocation,
fully initialised for the whole length, no aliasing mutation for the lifetime, and a total size
under `isize::MAX`. A length check alone is not the contract — when reviewing, ask which of those
the comment actually establishes rather than accepting a bounds `assert!` as the whole argument.

```bash
rg -n 'unsafe\s*\{' -B2 --glob "*.rs"
rg -n 'from_raw_parts|get_unchecked|transmute|set_len' --glob "*.rs"
```

`#![forbid(unsafe_code)]` in a crate root is a strong positive signal — note it in the report.

## 2. Panics as Denial of Service

**Severity if violated**: High in a service, Medium in a CLI

A panic in a request handler aborts that request; in a worker or with `panic = "abort"` it takes
the process down. This is the most common real vulnerability in otherwise-safe Rust.

### MUST
- MUST NOT `unwrap`, `expect`, or index directly into a collection with a value derived from
  input. Use `get`, `ok_or`, and `?`.
- MUST bound arithmetic on input-derived values. Under the **default** profiles a debug build
  panics on overflow and a release build wraps silently, so the same code is a crash in one and a
  wrong number in the other (measured on rustc 1.91.0 with a runtime value). Read
  `[profile.*] overflow-checks` before relying on either behaviour — it can be turned on for
  release or off for debug, which changes which of the two failures you are looking at.
- MUST NOT slice with input-derived ranges (`&buf[a..b]`) without checking the bounds; slicing
  panics, and it also panics on a non-char-boundary index into a `&str`.

```rust
// BAD — three panic paths on one line
let value = &body[start..end].parse::<u32>().unwrap();

// GOOD
let slice = body.get(start..end).ok_or(Error::BadRange)?;
let value: u32 = slice.parse().map_err(|_| Error::BadInput)?;
```

```bash
rg -n '\.unwrap\(\)|\.expect\(' --glob "*.rs" -g '!tests/**' -g '!benches/**'
rg -n 'as u\d+|as i\d+' --glob "*.rs"      # silent truncation on narrowing casts
```

`checked_*`, `saturating_*`, and `try_into()` are the answers for arithmetic. A bare `as` cast is
only a defect when it **narrows or goes out of range** — `u8 as u32` is lossless and not a
finding, while `300i32 as u8` is `44` (measured) and `-1i32 as usize` is enormous. Flag the
narrowing and signed↔unsigned cases where the value comes from input, and use `try_into()` there.

## 3. Command Execution

**Severity if violated**: Critical

`std::process::Command` takes arguments as a list and does **not** invoke a shell, so the injection
shape only appears when someone reintroduces one.

### MUST
- MUST NOT pass user input inside a string handed to `sh -c` or `cmd /c`.
- MUST prepend `--` where the target program supports it, so a value starting with `-` cannot
  become an option.
- MUST NOT let input choose the executable without an allowlist.

```rust
// BAD — the shell is back
Command::new("sh").arg("-c").arg(format!("convert {user_file} out.png"));

// GOOD
Command::new("convert").arg("--").arg(&user_file).arg("out.png");
```

```bash
rg -n 'Command::new\("(sh|bash|cmd|powershell)"' --glob "*.rs"
```

## 4. Path Handling

**Severity if violated**: Critical

### MUST
- MUST verify containment after canonicalising, not by inspecting the input string.
- MUST NOT join user input onto a root without checking — `PathBuf::push` with an **absolute**
  path replaces the whole path, the same trap as Python's `os.path.join`.
- MUST canonicalise both the root and the target; comparing a canonical target against a raw root
  string rejects legitimate paths whenever the root itself is a symlink.

```rust
// BAD — push with "/etc/passwd" discards `root` entirely
let mut p = root.clone();
p.push(user_path);

// GOOD
let root = root.canonicalize()?;
let target = root.join(user_path).canonicalize()?;   // errors if absent — handle
if !target.starts_with(&root) {
    return Err(Error::OutsideRoot);
}
```

`Path::starts_with` compares whole components, so it does not have the `/srv/app-backup` prefix
bug that a string `startsWith` has in other languages. It is still only correct on canonical
paths.

Archive extraction is the same defect with a different door: a `tar` or `zip` member named
`../../etc/passwd` escapes the destination unless every member is validated.

## 5. SQL and Query Construction

**Severity if violated**: Critical

### MUST
- MUST bind every value — `sqlx::query!`, `query.bind(...)`, or the driver's placeholder API.
- MUST NOT build SQL with `format!`, `+`, or `write!` where any part is user input.
- MUST allowlist identifiers (table, column, sort direction); a bind cannot carry one.

```rust
// BAD
sqlx::query(&format!("SELECT * FROM users WHERE email = '{email}'"))

// GOOD — compile-time checked against the schema
sqlx::query!("SELECT * FROM users WHERE email = $1", email)
```

`sqlx::query!` verifies the SQL at compile time; `sqlx::query` with a runtime string does not.
Diesel's `sql_query` and any `.raw` escape hatch are what to search for.

```bash
rg -n 'query\(&?format!|sql_query\(|execute\(&?format!' --glob "*.rs"
```

## 6. Deserialization and Resource Limits

**Severity if violated**: High

Rust's deserializers do not execute arbitrary code the way `pickle` does, so the risk here is
**resource exhaustion and logic confusion**, not RCE.

### MUST
- MUST bound the request body before deserializing — an unbounded `serde_json::from_reader` on a
  socket lets one request drive allocation.
- MUST bound any length field read from input before it becomes a `Vec::with_capacity` or a
  `reserve`.
- SHOULD use `#[serde(deny_unknown_fields)]` where an unexpected field would mean the caller and
  the server disagree about the request — mass-assignment shapes and authorization payloads.
  It is a deliberate trade-off, not a blanket rule: it also breaks forward compatibility for any
  API whose clients may send fields a newer version added. Report its absence where the struct
  drives a privilege decision; do not report it on every DTO.
- MUST NOT trust a `usize` decoded from input as a count or an index.

```rust
// BAD — the message decides the allocation
let mut buf = Vec::with_capacity(header.len as usize);

// GOOD
if header.len as usize > MAX_FRAME { return Err(Error::TooLarge); }
let mut buf = Vec::with_capacity(header.len as usize);
```

Untrusted-input parsers deserve fuzzing; note its absence where the crate parses a wire format.

## 7. Dependency & Supply Chain

**Severity if violated**: High

### MUST
- MUST commit `Cargo.lock` for a binary or service, and treat a change to it as review scope.
- MUST review newly added or major-bumped crates in the diff — including a new `build.rs`, which
  **runs arbitrary code at build time** and is the closest Rust analogue to an npm lifecycle
  script.
- MUST NOT depend on a git or path source in a release build without saying why; those bypass the
  registry's immutability.
- MUST check for a crate name one edit away from a popular one (typosquatting).

**Untrusted-diff rule:** `cargo audit` is a cargo subcommand, so cargo resolves the project's
`.cargo/config.toml` (and the extensionless `.cargo/config`) before the subcommand runs — the
same `build.rustc`, `rustc-wrapper`, `credential-provider`, and `[alias]` surface that makes
`clippy` risky. An `[alias] audit = "run --bin whatever"` replaces the command outright.
Reading `Cargo.lock` is not the whole story. Run the cargo-config precheck in
`code-quality-review`'s `rust-quality.md` first, and for a diff you would not execute record
this block as `skipped-untrusted-execution`.

```bash
# Known advisories against the lockfile. Reads Cargo.lock; writes nothing to the crate.
cargo audit

# Build scripts and proc macros in the dependency graph — both run at build time
rg -n '^\s*build\s*=' Cargo.toml
rg -n 'proc-macro\s*=\s*true' --glob "*/Cargo.toml"

# Non-registry sources
rg -n '(git|path)\s*=' Cargo.toml
```

**Read-only:** skip every command in this block; record them as `skipped-read-only`.

```bash
cargo audit fix          # rewrites Cargo.toml / Cargo.lock
cargo update             # rewrites Cargo.lock
```

`cargo-audit` reports **unmaintained** crates alongside vulnerabilities. Unmaintained is a real
finding but not a vulnerability — report it as its own category rather than folding it in.

## 8. Secrets & Configuration

**Severity if violated**: High

### MUST
- MUST read secrets from the environment or a secret manager, never from source — a Rust binary
  ships its string literals, so a hardcoded key is recoverable with `strings`.
- MUST NOT log structures that carry credentials. `#[derive(Debug)]` on a config or request struct
  prints every field, and one `tracing::debug!` then puts the token in the log; implement `Debug`
  manually or wrap the field in a redacting type.
- MUST fail closed when a required secret is missing.

```rust
// BAD — every log line with this struct leaks the token
#[derive(Debug)]
struct Config { api_token: String }

// GOOD — the field cannot be printed by accident
struct Config { api_token: Secret<String> }
```

```bash
rg -n '(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*"' --glob "*.rs"
rg -n '#\[derive\([^)]*Debug' -A6 --glob "*.rs" | rg -i 'token|secret|password|key'
```

## 9. Cryptography and Randomness

**Severity if violated**: High

### MUST
- MUST use a cryptographically secure generator for tokens and session identifiers.
  `OsRng`, `getrandom`, **and `thread_rng()`** all qualify — `ThreadRng` implements `CryptoRng`
  (verified in rand 0.8.7: `impl CryptoRng for ThreadRng`), so flagging it is a false positive.
  What does not qualify: `SmallRng`, and any generator seeded from a value the code chose
  (`StdRng::seed_from_u64`, a timestamp, a counter).
- MUST compare secrets in constant time (`subtle::ConstantTimeEq`), never with `==`.
- MUST NOT disable certificate verification
  (`danger_accept_invalid_certs`, a custom always-accepting verifier) outside a test.
- MUST NOT use MD5 or SHA-1 for anything security-bearing.

```bash
rg -n 'SmallRng|seed_from_u64|from_seed\(' --glob "*.rs"
rg -n 'danger_accept_invalid_certs|danger_accept_invalid_hostnames' --glob "*.rs"
```

Rust's type system does not protect against choosing the wrong primitive. Judge by which
generator and which comparison the code uses, not by whether it compiles.
