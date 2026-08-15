# Python Quality Reference

Tooling and manual patterns for Python code — a web service, a CLI, a data job, or a library.
Security rules live in `web-security-review/references/python-security.md`; this file is about
correctness, clarity, and cost.

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

**Detection signals** — any one puts Python in scope:

| Signal | Meaning |
|---|---|
| `pyproject.toml` | the modern manifest; read `[project]`, `[tool.ruff]`, `[tool.mypy]` |
| `setup.py` / `setup.cfg` | older packaging; still authoritative for the package layout |
| `requirements*.txt` | dependency pins without a manifest |
| `*.py` with no manifest | a loose script — still reviewable, but tool config comes from defaults |

**The project root is the directory holding the manifest**, not the repository root. A monorepo
with `services/api/pyproject.toml` and `tools/etl/pyproject.toml` has two roots, each with its
own tool configuration and its own Python version.

**Exclude from review**: `.venv/`, `venv/`, `site-packages/`, `__pycache__/`, `.mypy_cache/`,
`.ruff_cache/`, `build/`, `dist/`, `*.egg-info/`, and any generated `_pb2.py` / `_pb2_grpc.py`.
Findings in vendored or generated code are noise — report the generator instead.

**No reference for a language means it is unreviewed, not reviewed-by-analogy.** See `SKILL.md`.

## 1. Version Resolution

Read, in this order, and stop at the first that answers:

1. `pyproject.toml` → `[project] requires-python` — the declared floor
2. `.python-version` (pyenv, uv) — what the developer actually runs
3. `tox.ini` / `noxfile.py` / CI workflow matrix — what the project tests against
4. `python3 --version` in the environment — the fallback, and the least authoritative

**The version changes which findings are real.** `match` statements need 3.10; `X | Y` in
annotations at runtime needs 3.10; `tomllib` needs 3.11; `@override` needs 3.12. Recommending
a construct the project's floor does not support is a wrong finding, so state the floor you
worked from in the report.

Also read the packaging tool in use — `uv.lock`, `poetry.lock`, `Pipfile.lock`, or a bare
`requirements.txt`. It decides how a tool would be invoked (`uv run ruff`, `poetry run ruff`)
and whether the lock is part of the review scope.

## 2. Tool Roles

| Role | Tool | Config the project may already carry |
|---|---|---|
| Lint + format | **ruff** | `[tool.ruff]` in `pyproject.toml`, or `ruff.toml` / `.ruff.toml` |
| Type checking | **mypy** or **pyright** | `[tool.mypy]`, `mypy.ini`, `setup.cfg`, or `pyrightconfig.json` |
| Dead code | **vulture** | `.vulture` allowlist, or `[tool.vulture]` |
| Complexity | **radon** | usually invoked with flags, not config |

**Project configuration wins over anything suggested here.** If `[tool.ruff]` selects a rule set,
run ruff with that config and do not override the selection — a finding the project has
deliberately disabled is not a finding.

ruff replaces flake8, isort, pyupgrade, and Black in one binary; when a project still runs those
separately, review with what the project runs rather than introducing a tool it has not adopted.

**No tool for a role is `unavailable`, not a silent gap.** A project with no type checker gets
`type checking: unavailable — no mypy/pyright configuration` in the report, which is itself
worth saying.

## 3. Availability and Authority

Check before running:

```bash
command -v ruff mypy pyright vulture radon
# Project-local installs live in the virtualenv, not on PATH:
ls .venv/bin/ 2>/dev/null | grep -E '^(ruff|mypy|pyright|vulture|radon)$'
```

```powershell
Get-Command ruff, mypy, pyright -ErrorAction SilentlyContinue
Get-ChildItem .venv\Scripts\ -ErrorAction SilentlyContinue |
  Where-Object Name -match '^(ruff|mypy|pyright|vulture|radon)\.exe$'
```

**Read-only:** skip every command in this block; record them as `skipped-read-only`.

```bash
# Normal mode only. Prefer the project's own tooling — uv, then pip in its virtualenv.
# `uv tool install` takes ONE package per invocation (verified on uv 0.9.17: a second
# positional argument is rejected with `unexpected argument`).
uv tool install ruff
uv tool install mypy
uv tool install vulture
uv tool install radon

# Or into the project's environment
python3 -m pip install ruff mypy vulture radon
```

Under read-only, record the withheld install as `skipped-read-only` and each role it would have
enabled as `skipped-not-installed`. The two are different facts: the command was withheld, and
the check became impossible.

## 4. Execution

**Every command below must leave the working tree unchanged.** Two of these tools write a cache
directory into the project by default, and that is a file the review promised not to create.

### ruff — lint

```bash
# `--no-cache` also suppresses the write: measured on ruff 0.16.3, a plain `ruff check` creates
# `.ruff_cache/` in the project root while `--no-cache` creates nothing. (The `--help` text says
# "disable cache reads"; the observed behaviour is that no cache directory appears.)
ruff check --no-cache --output-format=concise .

# Only the changed files
ruff check --no-cache --output-format=concise path/to/file.py
```

```bash
# Formatting drift, reported not applied. `--check` never rewrites, but the cache still applies.
ruff format --no-cache --check --diff .
```

**Read-only:** skip every command in this block; record them as `skipped-read-only`.

```bash
# Rewrites source — never under a read-only request
ruff check --fix .
ruff format .
```

### mypy — type checking

```bash
# The read-only-safe form: mypy documents the null device as the way to disable the cache
# entirely, so nothing is written anywhere — not just outside the project.
mypy --cache-dir=/dev/null .
```

```powershell
mypy --cache-dir=nul .
```

**`--no-incremental` does not do what its name suggests.** Measured on mypy 2.3.1, a run with
`--no-incremental` still creates `.mypy_cache/` in the project root. Only `--cache-dir` moves it.
This is the opposite of the TypeScript rule in `js-toolchain.md`, where `--incremental false` is
the safe form — do not carry the habit across.

Read the project's strictness before reporting. `[tool.mypy] strict = true` and a bare default
produce different findings from the same code, and a strictness gap explains a class of runtime
errors better than any single line (see §5).

### pyright — type checking (alternative)

```bash
# Writes no cache into the project; `--outputjson` goes to stdout, not a file.
pyright --outputjson
```

### vulture — dead code

```bash
vulture . --min-confidence 60      # default: includes unused functions and classes
vulture . --min-confidence 90      # unused imports and variables only
```

**Know what the floor throws away before choosing one.** Measured on vulture 2.16, an unused
function scores 60% and an unused import 90% — so `--min-confidence 80` reports imports and
silently drops every unused function, which is usually the finding worth having.

Choose by what the code is: in an **application** run the default 60 and treat the results as
real, since nothing outside the repository calls into it. In a **library** the same 60%
findings are mostly public API that consumers call from outside the analysis, so verify each
against the exported surface (`__all__`, the documented API) before reporting one.

Either way, say which floor was applied — a vulture run with no findings means nothing without it.

vulture exits `3` when it reports dead code, `0` when it does not. Do not read `3` as a crash.

### radon — complexity

```bash
radon cc . --min C --average        # cyclomatic complexity, C and worse
radon mi . --min B                  # maintainability index
```

### Interpreting exit codes

| Tool | `0` | non-zero |
|---|---|---|
| ruff | no findings | findings (`1`) or a usage error (`2`) |
| mypy | clean | type errors (`1`) or a crash (`2`) — distinguish, a crash is `execution-error` |
| pyright | clean | findings, or a config error |
| vulture / radon | ran | vulture returns `3` when it found dead code |

An exit code of `2` from ruff or mypy is a **run-state of `execution-error`**, not a finding
count of zero. Never report "no issues" from a run that failed to start.

## 5. Manual Patterns

What the tools do not catch.

### Mutable default arguments

```python
# BAD — the list is created once, at definition, and shared by every call
def append_to(item, target=[]):
    target.append(item)
    return target

# GOOD
def append_to(item, target=None):
    target = [] if target is None else target
```

ruff's `B006` catches the literal form; it does not catch the same bug built through a default
factory or a class attribute:

```python
# BAD — one dict shared by every instance
class Cache:
    entries = {}
```

### Broad exception handling

```python
# BAD — swallows every programming error: a TypeError from a refactor now reads as
# "compute is unavailable", and the traceback is gone
try:
    result = compute()
except Exception:
    result = None
```

```python
# WORSE — a bare except also catches BaseException, so KeyboardInterrupt and SystemExit
# stop working. `except Exception` does NOT catch those two; the bare form does.
try:
    result = compute()
except:
    pass
```

```python
# GOOD — name what you expect, and let the rest propagate
try:
    result = compute()
except (ValueError, KeyError) as exc:
    logger.warning("compute failed: %s", exc)
    result = None
```

(The three are separate blocks on purpose: a bare `except:` after another handler is a
`SyntaxError` — `default 'except:' must be last`.)

Flag any `except` that discards the exception without logging it. The cost lands later, in an
incident where the traceback does not exist.

### Late-binding closures in loops

```python
# BAD — every callback sees the final value of i
handlers = [lambda: process(i) for i in range(3)]

# GOOD — bind at definition
handlers = [lambda i=i: process(i) for i in range(3)]
```

### Evaluation order and cost

```python
# BAD — the expensive call runs for every row, even when the cheap check would reject it
for row in rows:
    if fetch_profile(row.user_id).is_active and row.status == "pending":
        ...

# GOOD — cheap, local, high-rejection checks first
for row in rows:
    if row.status == "pending" and fetch_profile(row.user_id).is_active:
        ...
```

The same applies to comprehension filters and to `any()`/`all()` generators — `and`/`or`
short-circuit, so ordering is a real optimisation, not a style preference.

### Queries and I/O inside loops

```python
# BAD — one round trip per row (the N+1 shape, ORM or not)
for order in orders:
    customer = db.query("SELECT * FROM customers WHERE id = ?", order.customer_id)

# GOOD — one round trip
ids = {o.customer_id for o in orders}
customers = db.query_many("SELECT * FROM customers WHERE id IN (...)", ids)
```

### String building in a loop

```python
# BAD — quadratic; each += copies the whole string
out = ""
for line in lines:
    out += line + "\n"

# GOOD
out = "\n".join(lines) + "\n"
```

### Comments that will go stale

Follow the same rule as every other language here: delete comments that restate the code, keep
comments that explain a non-obvious *why*. A docstring whose `:param:` list no longer matches the
signature is worse than no docstring — it is a confident lie.

### Type annotations that claim more than they check

```python
# BAD — annotated, but nothing verifies it, and the body contradicts it
def total(items: list[int]) -> int:
    return sum(items) / len(items)      # returns float
```

Annotations without a type checker in CI are documentation, not a guarantee. When a project
annotates heavily but runs no checker, say so once as a finding about the pipeline rather than
line by line.

## 6. Severity Mapping

| Finding | Severity |
|---|---|
| Mutable default / shared class-level container | High — it is a latent data-corruption bug |
| Bare `except` or `except Exception` that discards the error | High |
| N+1 query or I/O in a loop on a request path | High |
| Quadratic string or list building on unbounded input | Medium–High by input size |
| Evaluation order (expensive check first) | Medium |
| `radon cc` rank D or worse | Medium |
| Dead code (vulture ≥80 confidence) | Low |
| Formatting drift where the project pins a formatter | Low |
| Stale or contradictory docstring | Low, High if it documents a security-relevant contract |

Severity follows impact, not the tool's own label — a ruff `E` and a ruff `F` say nothing about
how much the defect costs. State the reasoning for anything above Medium.

**Run states** — every invocation above resolves to exactly one of `passed`, `findings`,
`skipped-read-only`, `skipped-not-installed`, `unavailable`, `timeout`, `execution-error`, as
defined in `SKILL.md`. A review where mypy was never installed reports type checking as
`skipped-not-installed`, and the verdict says which class of defect therefore went unchecked.
