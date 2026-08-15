# Python Security Reference

**Language axis.** These are properties of the Python runtime and its package ecosystem — they
hold whether the process serves HTTP, runs as a CLI, or ships as a library. Pair this file with
the **surface axis** reference for what the process actually exposes:
`http-server-security.md`, `browser-security.md`, `native-security.md`. Load every surface that
applies; a package that serves an API *and* installs a console script needs both.

**Severity if violated** is stated per section. As in `php-backend-security.md`, the same `MUST`
grammar carries different severities — the impact decides, not the wording.

## Table of Contents
1. [Command Execution](#1-command-execution)
2. [Path Handling](#2-path-handling)
3. [Deserialization & Dynamic Evaluation](#3-deserialization--dynamic-evaluation)
4. [SQL and Query Construction](#4-sql-and-query-construction)
5. [Dependency & Supply Chain](#5-dependency--supply-chain)
6. [Secrets & Configuration](#6-secrets--configuration)
7. [Cryptography and Randomness](#7-cryptography-and-randomness)
8. [Template and Markup Rendering](#8-template-and-markup-rendering)

---

## 1. Command Execution

**Severity if violated**: Critical

### MUST
- MUST NOT pass user input into `subprocess` with `shell=True`, `os.system`, or `os.popen`.
- MUST use an **argument list**, never a concatenated or f-string command line.
- MUST validate the executable against an allowlist when the program name itself is dynamic.

```python
# BAD — a shell parses this; `; rm -rf /` in the filename is a command
subprocess.run(f"convert {user_file} out.png", shell=True)

# BETTER — no shell, arguments stay arguments
subprocess.run(["convert", user_file, "out.png"], check=True)

# GOOD — also stops the target program reading the value as an option
subprocess.run(["convert", "--", user_file, "out.png"], check=True)
```

**An argument list is not the end of the check.** It stops the *shell* from parsing the value; it
does not stop the *target program*. A `user_file` beginning with `-` is read as an option. Where
the program supports `--`, put it before user values; where it does not, validate against what
that program accepts.

`shlex.quote` is for building a shell string when you truly need one — it is not a substitute for
`shell=False`, and it is **not correct on Windows**, whose command-line parsing rules differ.

```bash
rg -n "shell\s*=\s*True|os\.system|os\.popen|commands\." --glob "*.py"
rg -n "subprocess\.(run|Popen|call|check_output)" -A2 --glob "*.py"
```

## 2. Path Handling

**Severity if violated**: Critical

### MUST
- MUST resolve user-supplied paths and verify the result stays inside the intended root.
- MUST NOT rely on stripping `../` — resolution before the check is what makes it sound.
- MUST reject absolute paths when a relative one was expected.

```python
# BAD — os.path.join with an absolute second argument discards the root entirely
target = os.path.join(ROOT, user_path)     # user_path="/etc/passwd" → "/etc/passwd"

# GOOD — resolve, then prove containment (resolve() follows symlinks, so this covers links)
root = Path(ROOT).resolve()
target = (root / user_path).resolve()
if not target.is_relative_to(root):        # Python 3.9+
    raise ValueError("outside root")
```

Two traps specific to Python:

- `os.path.join(a, b)` **returns `b` when `b` is absolute.** This is documented behaviour and the
  single most common path defect in Python code.
- `Path.resolve()` follows symlinks, so containment checked *after* it also covers link escape.
  `os.path.normpath` does **not** — it is lexical only, like the JS `path.resolve` case in
  `node-security.md` §2.

Archive extraction is the same class of bug with a different entry point, and the two stdlib
modules do **not** behave the same — measured on 3.12.3:

- `zipfile.extractall` sanitises member names: a `../escaped.txt` member lands inside the
  destination as `escaped.txt`, and a leading `/` is stripped. Traversal is not the risk here;
  zip bombs, symlink members, and colliding names still are.
- `tarfile.extractall` **does** write outside the destination unless a filter says otherwise.
  `filter="data"` rejects it (`OutsideDestinationError`), and it is the filter to require.

Check the filter's availability with `hasattr(tarfile, "data_filter")` rather than a version
comparison — the filters were backported to security-fix releases of older branches, so a version
test reports "unsupported" on runtimes that support it.

```bash
rg -n "extractall|os\.path\.join\(" --glob "*.py"
```

## 3. Deserialization & Dynamic Evaluation

**Severity if violated**: Critical

### MUST
- MUST NOT unpickle data that crossed a trust boundary. `pickle.loads` executes code by design —
  this is not a bug to be patched, it is what the format does.
- MUST NOT pass untrusted input to `eval`, `exec`, or `compile`.
- MUST use `yaml.safe_load`, never `yaml.load` without a safe loader.
- MUST treat `marshal`, `shelve`, `dill`, and `jsonpickle` on untrusted input as the same defect
  as `pickle`.

```python
# BAD — remote code execution, by design
config = pickle.loads(request.data)

# BAD — constructs arbitrary Python objects
config = yaml.load(payload)

# GOOD
config = yaml.safe_load(payload)
```

`ast.literal_eval` evaluates literals only — it does **not** execute arbitrary code, and that is
a real difference from `eval`. It is still not "safe for untrusted input": the CPython docs warn
that a sufficiently large or complex string can crash the interpreter through memory or C-stack
exhaustion. Treat it as *not RCE*, not as *harmless*: bound the input length before calling it, or
use `json.loads` where the format allows.

```bash
rg -n "pickle\.loads?|yaml\.load\(|\beval\(|\bexec\(|jsonpickle|dill\." --glob "*.py"
```

## 4. SQL and Query Construction

**Severity if violated**: Critical

### MUST
- MUST parameterise every value that reaches SQL. The DB-API placeholder (`?`, `%s`, `:name`)
  depends on the driver — use the one the driver documents, not string formatting.
- MUST NOT build SQL with f-strings, `%`, `.format()`, or `+` where any part is user input.
- MUST allowlist identifiers (table, column, sort direction) — placeholders **cannot** bind an
  identifier, so this is the one case that needs a lookup table rather than a parameter.

```python
# BAD — f-string into SQL
cur.execute(f"SELECT * FROM users WHERE email = '{email}'")

# GOOD — the driver binds the value
cur.execute("SELECT * FROM users WHERE email = %s", (email,))

# GOOD — identifiers cannot be bound, so map them
COLUMNS = {"name": "name", "created": "created_at"}
cur.execute(f"SELECT * FROM users ORDER BY {COLUMNS[sort_key]}")   # KeyError on anything else
```

In an ORM, the escape hatches are what to look for: SQLAlchemy `text()` with interpolation,
Django `.extra()` / `.raw()` / `RawSQL`, and any `filter(**{user_key: value})` built from request
data.

```bash
rg -n "execute\(f\"|execute\(.*%\s*\(|\.raw\(|\.extra\(|text\(f\"" --glob "*.py"
```

## 5. Dependency & Supply Chain

**Severity if violated**: High

### MUST
- MUST pin and lock dependencies (`uv.lock`, `poetry.lock`, or a hash-pinned
  `requirements.txt`), so the installed tree is the reviewed tree.
- MUST review newly added or major-bumped dependencies in the diff — a lockfile change is part of
  the security scope, not noise.
- MUST NOT install from a URL, a VCS ref, or an unpinned index in production configuration.
- MUST treat a package whose name is one edit away from a popular one as a finding until
  confirmed (typosquatting is the routine attack here).

`setup.py` executes on install for a source distribution, so a new dependency shipping one is
worth reading — the Python analogue of an npm lifecycle script.

**Auditing a requirements file is not a read-only operation by default.** pip-audit's own
[security model](https://github.com/pypa/pip-audit#security-model) states that auditing a
requirements input carries the same trust boundary as `pip install -r` on it: resolving
dependencies can invoke build backends and metadata hooks from the packages being resolved,
with the reviewer's permissions. On a branch under review — which is exactly the untrusted case
— that is code execution on the reviewer's machine.

```bash
# Audit the declared pins only, with no resolution: the trust boundary stays at reading the file.
pip-audit --no-deps --disable-pip -r requirements.txt

# Hash pinning present? (a hashed, fully-pinned file is what makes --no-deps sound)
rg -n "^\s*--hash=|^\s*[A-Za-z0-9_.-]+==" requirements*.txt
```

`--no-deps` skips resolution, so it audits what the file names and nothing transitive — say so in
the report rather than implying full coverage. Auditing the **active environment**
(`pip-audit` with no `-r`) is safe in the same sense: it reads what is already installed.

**Read-only:** skip every command in this block; record them as `skipped-read-only`.

```bash
# Full resolution — runs build backends from the audited packages
pip-audit -r requirements.txt
# `--fix` rewrites requirements
pip-audit --fix
```

**`pip-audit --dry-run` does not audit.** It resolves and reports what it *would* have audited,
then prints `No known vulnerabilities found` — a line that reads exactly like a clean result.
Never record a `--dry-run` as a passing audit; note also that it still performs the resolution
described above.

## 6. Secrets & Configuration

**Severity if violated**: High

### MUST
- MUST read secrets from the environment or a secret manager, never from source.
- MUST NOT log request objects, `os.environ`, or exception objects that carry credentials.
- MUST NOT ship `.env`, `*.pem`, or a service-account JSON in the built package — check
  `MANIFEST.in`, `package_data`, and the sdist contents.
- MUST fail closed when a required secret is missing rather than falling back to a default.

```python
# BAD — a default that silently downgrades security
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret")

# GOOD
SECRET_KEY = os.environ["SECRET_KEY"]      # KeyError at startup beats a forged session later
```

Django-specific and worth grepping for directly: `DEBUG = True` reachable in production, an empty
`ALLOWED_HOSTS`, and a hardcoded `SECRET_KEY` in `settings.py`.

```bash
rg -n "SECRET_KEY|API_KEY|PASSWORD|TOKEN" --glob "*.py" -i | rg -v "os\.environ|getenv"
rg -n "DEBUG\s*=\s*True|ALLOWED_HOSTS\s*=\s*\[\s*\]" --glob "*.py"
```

## 7. Cryptography and Randomness

**Severity if violated**: High

### MUST
- MUST use `secrets` for tokens, session identifiers, password resets, and anything an attacker
  should not predict. `random` is a Mersenne Twister — its state is recoverable from observed
  output, so `random.choice` for a reset token is a real vulnerability, not a style issue.
- MUST use `hmac.compare_digest` to compare secrets, never `==`.
- MUST NOT use `md5` or `sha1` for anything security-bearing; where a non-security digest is
  intended, say so with `usedforsecurity=False` (3.9+) so the reader can tell.
- MUST NOT disable certificate verification (`verify=False`, `ssl._create_unverified_context`).

```python
# BAD — predictable
token = "".join(random.choices(string.ascii_letters, k=32))

# GOOD
token = secrets.token_urlsafe(32)
```

```bash
rg -n "random\.(choice|randint|random|choices)|md5\(|sha1\(|verify\s*=\s*False" --glob "*.py"
```

## 8. Template and Markup Rendering

**Severity if violated**: **Critical** for template injection (it reaches Python execution),
High for the escaping rules below it

### MUST
- MUST NOT render a template built from user input — Jinja2 `Template(user_input)` is server-side
  template injection. It reaches Python execution through attribute traversal, not just HTML, so
  report it as **Critical**, above the escaping findings in this section.
  A `SandboxedEnvironment` is the documented way to render untrusted template text and blocks that
  traversal; it is a mitigation to verify, not a reason to skip the finding, and escapes from it
  have been published. Say which environment the code uses.
- MUST NOT mark user data safe (`|safe`, `mark_safe`, `Markup(...)`) without a sanitiser that the
  reviewer can name.
- MUST keep autoescaping on. `Environment()` defaults to `autoescape=False` in Jinja2 —
  `select_autoescape()` is the correct construction for anything rendering HTML.

```python
# BAD — autoescape is off by default here
env = Environment(loader=FileSystemLoader("templates"))

# GOOD
env = Environment(loader=FileSystemLoader("templates"), autoescape=select_autoescape())
```

When the rendered output reaches a browser, the browser-side rules in `browser-security.md`
apply on top of this section.

```bash
rg -n "\|safe|mark_safe|Markup\(|Template\(" --glob "*.py" --glob "*.html" --glob "*.jinja*"
rg -n "Environment\(" -A2 --glob "*.py" | rg -v "autoescape"
```

---

## Running bandit

`bandit` covers a useful subset of the above mechanically, and writes nothing to the project
(measured on bandit 1.9.4).

```bash
bandit -r . -x ./tests,./.venv          # exclude tests: assert_used fires on every test file
bandit -r . -ll                          # medium severity and above
bandit -r . -f json                      # machine-readable, to stdout
```

Bandit's own severity is a starting point, not the verdict — it rates by pattern, and the impact
depends on whether the input is reachable from a trust boundary. Re-rate against the section
above and say which check produced the finding (`B602`, `B301`, …) so it can be looked up.
