# Rust Quality Reference

Tooling and manual patterns for Rust — a service, a CLI, or a library. Security rules live in
`web-security-review/references/rust-security.md`; this file is about correctness, clarity,
and cost.

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
| `Cargo.toml` | the crate (or workspace) root |
| `Cargo.lock` | committed for a binary, often absent for a library — this matters in §4 |
| `[workspace]` in `Cargo.toml` | several member crates under one lockfile |
| `rust-toolchain.toml` | the toolchain the project pins |

**Exclude from review**: `target/`, vendored sources under `vendor/`, and generated code —
anything produced by a `build.rs` or by `include!(concat!(env!("OUT_DIR"), ...))`. A finding in
generated output belongs to the generator.

## 1. Version Resolution

**Collect all of these; they answer different questions.**

| Question | Source |
|---|---|
| What is the **floor**? | `Cargo.toml` → `rust-version` (MSRV) — what consumers may rely on |
| What actually **runs**? | `rust-toolchain.toml` → `channel`, else `rustc --version` |
| What is **tested**? | the CI matrix — an MSRV job in particular |
| Which **dialect**? | `Cargo.toml` → `edition` (2015 / 2018 / 2021 / 2024) |

An MSRV with no CI job pinning it is unverified: the code compiles on the developer's stable
toolchain and breaks for the consumer who took the declared floor at its word. Say so once.

The MSRV decides whether a suggestion is usable: `let ... else` needs 1.65, `impl Trait` in
associated position needs 1.75, and edition 2024 changes closure capture and `unsafe` attribute
syntax. Recommending past the floor is a wrong finding — state the floor you worked from.

## 2. Tool Roles

| Role | Tool | Notes |
|---|---|---|
| Lint | **clippy** | ships with rustup; the correctness and perf groups matter most |
| Compile check | **`cargo check`** | type and borrow errors without producing a binary |
| Formatting | **rustfmt** (`cargo fmt`) | `--check` reports drift without touching files |
| Advisories | **cargo-audit** | see `rust-security.md` |
| License/source policy | **cargo-deny** | only when the project already configures it |

**Project configuration wins.** `clippy.toml`, `#![deny(...)]` in a crate root, and `[lints]` in
`Cargo.toml` are the project's own policy — respect them and do not report what they allowed.

## 3. Availability and Authority

```bash
command -v cargo rustc
cargo clippy --version 2>/dev/null       # absent unless the clippy component is installed
cargo fmt --version 2>/dev/null
```

```powershell
Get-Command cargo, rustc -ErrorAction SilentlyContinue
```

**Read-only:** skip every command in this block; record them as `skipped-read-only`.

```bash
# Normal mode only — these install toolchain components and binaries
rustup component add clippy rustfmt
cargo install cargo-audit
```

## 4. Execution

**Cargo writes two things into the project by default, and both matter here.** Measured on
cargo 1.91.0: a plain `cargo clippy` in a crate with no lockfile creates **`Cargo.lock`** in the
crate root and a **`target/`** directory beside it. `target/` is usually gitignored but still
consumes real disk; `Cargo.lock` in a library crate is a new untracked file the review created.

The read-only-safe invocation moves the build directory out and refuses to touch the lockfile:

```bash
# Both parts are required. CARGO_TARGET_DIR relocates the build output; --locked stops
# cargo from creating or updating Cargo.lock.
CARGO_TARGET_DIR="$(mktemp -d)" cargo clippy --locked --all-targets
CARGO_TARGET_DIR="$(mktemp -d)" cargo check --locked --all-targets
```

```powershell
$env:CARGO_TARGET_DIR = Join-Path $env:TEMP "cargo-review"
cargo clippy --locked --all-targets
```

**When there is no `Cargo.lock`, `--locked` fails with exit 101** and the message *"the lock file
… needs to be updated but --locked was passed to prevent this"*. That is the correct outcome, not
an error to work around: record linting as `skipped-read-only` and say it needs either write
permission or a committed lockfile. Do not drop `--locked` to make it run, and do not substitute
`--offline`, which still writes the lockfile.

```bash
# Formatting drift — reports, changes nothing. Exits 1 when files differ.
cargo fmt --check
```

**Read-only:** skip every command in this block; record them as `skipped-read-only`.

```bash
cargo fmt                       # rewrites source
cargo clippy --fix              # rewrites source
```

### Interpreting exit codes

| Command | `0` | non-zero |
|---|---|---|
| `cargo clippy` | **compiled — warnings may still exist** | `101` compile error, or any lint denied by the project |
| `cargo clippy -- -D warnings` | no warnings | `101` at least one warning |
| `cargo check` | compiles | `101` compile error |
| `cargo fmt --check` | formatted | `1` drift, and the diff is on stdout |

`cargo clippy` is the trap: it exits `0` with warnings present. Read the output. Adding
`-D warnings` turns them into a non-zero exit but also **overrides the project's own lint
policy**, so use it to get a signal, not to decide severity.

## 5. Manual Patterns

Rust's compiler already rejects most memory defects, so review effort belongs where the compiler
is silent: panics, blocking, and cost.

### Panic paths in library and service code

```rust
// BAD — a request with an unexpected shape takes the process down
let user = users.get(&id).unwrap();
let n: u32 = input.parse().expect("number");

// GOOD — the error becomes a value the caller can handle
let user = users.get(&id).ok_or(Error::NotFound)?;
let n: u32 = input.parse().map_err(|_| Error::BadInput)?;
```

Flag `unwrap`, `expect`, direct indexing (`v[i]`), integer division by a value from input, and
`slice[a..b]` where the bounds come from outside. In a `main` or a test, `unwrap` is fine — judge
by where it sits, and say so rather than reporting every occurrence.

### Blocking inside async

```rust
// BAD — blocks the executor thread; every other task on it stalls
async fn handler() {
    let data = std::fs::read_to_string("big.json").unwrap();
    std::thread::sleep(Duration::from_secs(1));
}
```

Flag synchronous file and network I/O, `std::thread::sleep`, and long CPU work inside an `async fn`
or a `.await` chain. The fix is the async equivalent or `spawn_blocking`. Also flag a
`std::sync::Mutex` guard held across an `.await` — it is not designed for that and deadlocks under
load.

### Unnecessary allocation and cloning

```rust
// BAD — allocates a String for a comparison that borrows fine
if name.to_string() == other { ... }

// BAD — clone in a loop where a reference would do
for item in &items { process(item.clone()); }
```

Clippy catches many of these (`redundant_clone`, `needless_collect`). What it misses is the
architectural version: a function taking `String` where `&str` would serve, forcing every caller
to allocate.

### Collecting a whole iterator to read one value

```rust
// BAD — materialises everything to take the first
let first = items.iter().map(expensive).collect::<Vec<_>>()[0];

// GOOD — lazy; expensive runs once
let first = items.iter().map(expensive).next();
```

### Evaluation order and cost

`&&` and `||` short-circuit, so put the cheap, high-rejection check first — the same rule as every
other language here. In Rust the expensive side is often a `.clone()` or a lock acquisition that
the reader does not register as expensive.

### `unsafe` blocks

Every `unsafe` block needs a comment stating the invariant that makes it sound. An `unsafe` block
with no such comment is a finding on its own, independent of whether it is correct today — the
next editor has nothing to preserve. Details in `rust-security.md`.

### Comments

Same rule as every other language: keep the non-obvious *why*, drop restatements. Rust adds one
worth enforcing — a doc comment (`///`) with an example is compiled and run by `cargo test`, so a
stale example is a failing test, not just wrong prose. Say when an example no longer matches the
signature.

## 6. Severity Mapping

| Finding | Severity |
|---|---|
| `unwrap`/`expect`/indexing on input-derived data in a service or library | High — it is a remote panic |
| Blocking call inside `async` on a request path | High |
| `std::sync::Mutex` guard held across `.await` | High |
| `unsafe` block with no safety comment | Medium, High when it dereferences a raw pointer from input |
| Allocation-heavy API shape (`String` where `&str` fits) on a hot path | Medium |
| Collect-then-index instead of a lazy iterator | Medium |
| clippy `correctness` group | High |
| clippy `perf` / `complexity` group | Medium |
| clippy `style` / `pedantic` group | Low |
| Formatting drift (`cargo fmt --check`) | Low |

Severity follows impact. Clippy's own group names are a useful prior — `correctness` really does
mean "this is probably a bug" — but re-rate against reachability before reporting.

**An application and a published library carry different impact.** The same defect is rated by
who pays for it: in an application the blast radius ends at this deployment, while in a library
it reaches every consumer and cannot be rolled back by the author alone. Raise a severity one
step when the finding is in a **published library's public API or its documented behaviour** —
a panic reachable from a public function, an API shape that forces every caller to allocate, a
contract the docs promise and the code no longer honours. Lower nothing on that basis: an
application defect is not less real, it is only narrower.


**Run states** — `passed`, `findings`, `skipped-read-only`, `skipped-not-installed`,
`unavailable`, `timeout`, `execution-error`, as defined in `SKILL.md`. A crate with no lockfile
under a read-only review is `skipped-read-only`, never `passed`.
