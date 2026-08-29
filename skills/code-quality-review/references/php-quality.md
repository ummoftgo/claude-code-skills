# PHP Code Quality Reference

CLI tools and manual patterns for PHP quality review.

> **The read-only rule in `SKILL.md` overrides every instruction in this file.** Under a
> read-only request, no command here may install a tool, create a config file, write a
> report file, or auto-fix code — regardless of what an individual section says. Each
> write-causing command below carries its own read-only contract line; when one is
> skipped, record it in the report with its reason.

## Table of Contents
0. [PHP Version Resolution](#0-php-version-resolution)
1. [CLI Tool Setup](#1-cli-tool-setup)
2. [Running the Tools](#2-running-the-tools)
3. [Comment Quality](#3-comment-quality)
4. [Style Conventions](#4-style-conventions)
5. [Duplication](#5-duplication)
6. [Performance & Evaluation Order](#6-performance--evaluation-order)

---

## 0. PHP Version Resolution

Before running any PHP tool, verify that the CLI version matches the project's required version.
A mismatch causes PHPStan to report false positives for syntax and type features introduced in newer PHP versions.

### Detect project PHP version

```bash
# Extract required PHP version from composer.json (handles ^8.1, >=8.2, ~8.3, 8.3.* etc.)
PROJECT_PHP_VER=""
if [ -f composer.json ]; then
  PHP_CONSTRAINT=$(grep -oP '"php"\s*:\s*"\K[^"]+' composer.json 2>/dev/null | head -1)
  PROJECT_PHP_VER=$(echo "$PHP_CONSTRAINT" | grep -oP '\d+\.\d+' | head -1)
fi

# Current CLI version
CLI_PHP_VER=$(php -r 'echo PHP_MAJOR_VERSION . "." . PHP_MINOR_VERSION;' 2>/dev/null)
```

### Resolve PHP_CMD

```bash
PHP_CMD="php"   # default

if [ -n "$PROJECT_PHP_VER" ] && [ "$PROJECT_PHP_VER" != "$CLI_PHP_VER" ]; then
  echo "⚠ PHP version mismatch — project requires $PROJECT_PHP_VER, system php is $CLI_PHP_VER"

  # 1) Try versioned CLI first (php8.3, php8.4, ...)
  ALT_PHP="php${PROJECT_PHP_VER}"
  if command -v "$ALT_PHP" &>/dev/null; then
    PHP_CMD="$ALT_PHP"
    echo "✓ Using $ALT_PHP"
  else
    # 2) Ask the user
    echo "  Versioned CLI '$ALT_PHP' not found on PATH."
    echo "  Options:"
    echo "    a) Proceed with system php $CLI_PHP_VER (PHPStan may report false positives)"
    echo "    b) Provide the path to a php$PROJECT_PHP_VER binary"
    # Wait for user response; if they provide a path, set PHP_CMD accordingly:
    # PHP_CMD="/usr/local/bin/php8.3"
  fi
fi

echo "PHP_CMD=$PHP_CMD ($(${PHP_CMD} -r 'echo PHP_VERSION;' 2>/dev/null))"
```

### Derive the source directory

`SRC_DIR` comes from the first PSR-4 **directory value** in `composer.json`. PSR-4 maps namespace
keys (`"App\\"`) to directory values (`"src/"`), so read `array_values`, not `array_keys`.

```bash
SRC_DIR=$(php -r '$p=json_decode(file_get_contents("composer.json"),true)["autoload"]["psr-4"]??[];echo rtrim(array_values($p)[0]??""," /");') || SRC_DIR="src"
[ -n "$SRC_DIR" ] || SRC_DIR="src"      # fall back to src/, app/, or the project root
```

### Using PHP_CMD with tools

Only **PHPStan** uses the PHP binary for type analysis — the others are version-agnostic style checkers.

A project config takes precedence over `--level`. Use `if`/`else` rather than `&&`/`||`:
PHPStan exits non-zero when it finds errors, which would trigger a `||` fallback and run the
analysis twice.

PHPStan auto-discovers **six** config names, in this order — `.phpstan.neon`, `phpstan.neon`,
`.phpstan.neon.dist`, `phpstan.neon.dist`, `.phpstan.dist.neon`, `phpstan.dist.neon`. The three
dot-prefixed ones are the easy ones to forget: a project shipping only `.phpstan.neon` looks
unconfigured, the `--level=5` fallback then overrides the level the project actually set, and
the read-only cache isolation below never fires because it keys off the same variable.

**Under a read-only request the cache is relocated, not inspected.** PHPStan writes its result
cache to `sys_get_temp_dir()/phpstan` by default — outside the repository — but two settings move
it inside, `tmpDir` and `resultCachePath`, and the second is independent of the first. Finding
them reliably would mean parsing NEON across the whole `includes:` graph, and **unknown is not
safe**: a config that could not be read is exactly the case where a write would be a surprise.

So the block below does not look for them. It writes an override config outside the workspace
that `includes:` the project's own and points both cache keys at a temp directory. Whatever the
project declared, and in whichever of NEON's spellings, the cache lands outside.

```bash
# One variable decides everything below: which config PHPStan will actually use.
# Resolve it in PHPStan's own priority order — NOT with `ls | head -1`, which sorts
# alphabetically and would pick phpstan.dist.neon over phpstan.neon.
PHPSTAN_CONFIG=""
if [ -n "${PHPSTAN_EXPLICIT_CONFIG:-}" ]; then
  PHPSTAN_CONFIG="$PHPSTAN_EXPLICIT_CONFIG"          # set only when the run passes --configuration
else
  # PHPStan 2.x auto-discovers **six** names, in this order — the three dot-prefixed ones are
  # easy to forget, and missing them makes a configured project look unconfigured.
  for candidate in .phpstan.neon phpstan.neon .phpstan.neon.dist phpstan.neon.dist \
                   .phpstan.dist.neon phpstan.dist.neon; do
    [ -f "$candidate" ] && { PHPSTAN_CONFIG="$candidate"; break; }
  done
fi

# Trust gate — decided BEFORE PHPStan is invoked in **any** form. Every PHPStan entry point,
# `analyse` and `dump-parameters` alike, loads the config chain and runs `bootstrapFiles` and
# `.php` includes. So nothing may call PHPStan above this point.
# Set UNTRUSTED_DIFF=1 for a branch you would not execute. On a trusted branch the block is
# inert and nothing below changes.
EXEC_RISK=""
scan_for_exec() {
  local f="$1"
  if [ ! -r "$f" ]; then EXEC_RISK="$EXEC_RISK unreadable:$f"; return; fi
  grep -qE 'bootstrapFiles' "$f" && EXEC_RISK="$EXEC_RISK config-loads-code:$f"
  grep -qE '(autoload_files|autoload_directories)' "$f" &&
    EXEC_RISK="$EXEC_RISK legacy-autoload:$f"
  grep -qE '(^|[^a-zA-Z])(rules|services)[[:space:]]*[:=]' "$f" &&
    EXEC_RISK="$EXEC_RISK config-defines-extension:$f"
  grep -qE '\.php([^a-zA-Z0-9]|$)' "$f" && EXEC_RISK="$EXEC_RISK php-reference:$f"
}

if [ "${UNTRUSTED_DIFF:-0}" = "1" ]; then
  # **Any config at all is a stop.** Deciding a config harmless needs a real NEON parser over
  # the whole include graph, and the only parser at hand is inside PHPStan — which we must not
  # start yet. The scan below does not decide anything; it only says *why* in the report.
  [ -n "$PHPSTAN_CONFIG" ] && EXEC_RISK="$EXEC_RISK config-present:$PHPSTAN_CONFIG"
  for candidate in .phpstan.neon phpstan.neon .phpstan.neon.dist phpstan.neon.dist \
                   .phpstan.dist.neon phpstan.dist.neon "$PHPSTAN_CONFIG"; do
    [ -f "$candidate" ] || continue
    case "$candidate" in *.php) EXEC_RISK="$EXEC_RISK executable-config:$candidate" ;; esac
    scan_for_exec "$candidate"
  done
  # Composer runs every entry here, including dependencies' own `autoload.files`.
  # No `head`: a truncated list reads as a short list, and the entry that matters may be last.
  if [ -f vendor/composer/autoload_files.php ] &&
     grep -qE "=> .*'" vendor/composer/autoload_files.php; then
    EXEC_RISK="$EXEC_RISK composer-autoload-files"
  fi
  # `extra.phpstan.includes` is what `phpstan/extension-installer` activates. Matching a bare
  # `"phpstan"` would flag every package that merely depends on PHPStan — most projects.
  if [ -d vendor ] && $PHP_CMD -r '
      foreach (glob("vendor/*/*/composer.json") as $f) {
        $j = json_decode(@file_get_contents($f), true);
        if (!empty($j["extra"]["phpstan"]["includes"])) { exit(0); }
      }
      exit(1);
    ' 2>/dev/null; then
    EXEC_RISK="$EXEC_RISK phpstan-extension"
  fi
fi

# Read-only cache handling. **Do not try to judge where the cache would land — move it.**
# Judging means reading the config, and reading it soundly means a NEON parser: five rounds of
# review found five valid spellings a regex missed (`tmpDir = x`, a quoted `"tmpDir":`, a
# one-line `{tmpDir: x}`, a multi-line `includes: [...]`, a trailing `# comment` glued onto the
# value). Asking PHPStan instead is worse, not better: `dump-parameters` builds its DI container
# under the project's own `tmpDir`, so with `tmpDir: .cache` it writes four files into the
# repository *before* any gate could speak (measured on 2.1.42).
#
# An override config sidesteps all of it. It `includes:` the project's config so every project
# setting still applies, then sets both cache keys to a temp directory outside the workspace.
# Verified: nothing lands in the repository, the project's own `level` still applies, and even
# `TMPDIR` pointing inside the repository is neutralised.
if [ "${READ_ONLY:-0}" = "1" ] && [ -z "$EXEC_RISK" ]; then
  # Canonicalise the repository root once. A `.`, a `..`, or a symlinked parent
  # (`/var/run` → `/run`) makes a raw string prefix test wrong in both directions.
  REPO_ROOT=$(realpath -m "$PWD")
  PHPSTAN_TMP=$(mktemp -d) || PHPSTAN_TMP=""
  # `mktemp` honours `TMPDIR`. If that points inside the repository, our own scratch
  # directory lands there — the very thing this block exists to prevent. Retry outside.
  if [ -n "$PHPSTAN_TMP" ]; then
    case "$(realpath -m "$PHPSTAN_TMP")" in
      "$REPO_ROOT"|"$REPO_ROOT"/*)
        rm -rf "$PHPSTAN_TMP"
        PHPSTAN_TMP=$(TMPDIR=/tmp mktemp -d) || PHPSTAN_TMP=""
        [ -n "$PHPSTAN_TMP" ] && case "$(realpath -m "$PHPSTAN_TMP")" in
          "$REPO_ROOT"|"$REPO_ROOT"/*) rm -rf "$PHPSTAN_TMP"; PHPSTAN_TMP="" ;;
        esac
        ;;
    esac
  fi
  if [ -n "$PHPSTAN_TMP" ]; then
    PHPSTAN_OVERRIDE="$PHPSTAN_TMP/phpstan-review.neon"
    {
      # **Every path here is quoted and escaped the same way.** Unquoted, NEON reads ` #` as a
      # comment and `,` as a separator, so a project under `/srv/has #hash/` or `/srv/a,b/`
      # fails to parse. Quoted, an apostrophe in the path ends the string early — `O'Brien`
      # broke it until this escape went in. Single quotes with `''` doubling, not double
      # quotes: NEON treats `\` as an escape inside double quotes, which would break Windows
      # paths. All three measured on PHPStan 2.1.42.
      neon_quote() { printf "'%s'" "$(printf '%s' "$1" | sed "s/'/''/g")"; }

      if [ -n "$PHPSTAN_CONFIG" ]; then
        printf 'includes:\n    - %s\n' "$(neon_quote "$(realpath "$PHPSTAN_CONFIG")")"
      fi
      printf 'parameters:\n    tmpDir: %s\n' "$(neon_quote "$PHPSTAN_TMP/cache")"
      printf '    resultCachePath: %s\n' "$(neon_quote "$PHPSTAN_TMP/cache/resultCache.php")"
      [ -n "$PHPSTAN_CONFIG" ] || printf '    level: 5\n'
    } > "$PHPSTAN_OVERRIDE"
  fi
fi

# Clean the scratch directory up when the shell exits — it is outside the workspace, but a
# review that leaves one per run still litters the machine.
[ -n "${PHPSTAN_TMP:-}" ] && trap 'rm -rf "$PHPSTAN_TMP"' EXIT

# State line — the gates are driven by exported values, so a caller that forgot to set them
# would otherwise produce a normal-looking report with both gates inert. Say which mode ran.
echo "static analysis mode: read-only=${READ_ONLY:-0} untrusted=${UNTRUSTED_DIFF:-0}"

# PHPStan — run under the correct PHP binary
if [ -n "$EXEC_RISK" ]; then
  echo "static analysis: skipped-untrusted-execution — analysis would run project code ($EXEC_RISK)"
elif [ "${READ_ONLY:-0}" = "1" ] && [ -z "${PHPSTAN_OVERRIDE:-}" ]; then
  echo "static analysis: execution-error — no writable temp directory for the cache"
elif [ "${READ_ONLY:-0}" = "1" ]; then
  $PHP_CMD $(command -v phpstan) analyse "$SRC_DIR" \
    --configuration="$PHPSTAN_OVERRIDE" --no-progress --error-format=raw
elif [ -n "$PHPSTAN_CONFIG" ]; then
  $PHP_CMD $(command -v phpstan) analyse "$SRC_DIR" \
    --configuration="$PHPSTAN_CONFIG" --no-progress --error-format=raw
else
  $PHP_CMD $(command -v phpstan) analyse "$SRC_DIR" \
    --level=5 --no-progress --error-format=raw
fi

# phpcs / phpmd / phpcpd — version-agnostic; default php is fine
phpcs --report=full <src>
phpmd <src> text cleancode,codesize,naming,unusedcode
phpcpd <src>
```

The gate and the analysis read **the same `PHPSTAN_CONFIG`**.

### The same gate on Windows PowerShell

`SKILL.md` says a Windows-native install must not require WSL or Git Bash, so the Bash block
above cannot be the only form — without this, a PowerShell review runs PHPStan with no cache
isolation and no trust gate at all. The cache isolation is the same: discover the config among the
same six names and redirect both cache keys into a temp directory outside the workspace. The
trust gate is deliberately **stricter** here — see the reproduction note below.

**Reproduction status — read this before relying on it.** The Bash form was measured
end-to-end: every cache spelling, the trust gate, and the analysis actually running. This form
was checked for **PowerShell 5.1 syntax only**, because the Windows host used for development
has no PHP or PHPStan installed.

Two consequences, both deliberate:

- On an untrusted diff this form **stops unconditionally** (`windows-gate-unverified`). It does
  not try to reproduce the Bash gate's per-risk judgement, because nobody has measured whether
  it would. A Windows reviewer gets an explicit skip, not a silent gap.
- For an ordinary review it does isolate the cache, and that path is the one worth checking on
  first use: run it, then confirm `git status` is clean. If it is, this form can be promoted to
  measured support; if not, report what appeared.

Until that check happens, treat Windows PHPStan as **provisional**: safe to run on your own
branch, not to be relied on as the untrusted-diff barrier.

```powershell
# Every path written into the generated NEON goes through this. Single quotes so `\` stays
# literal (Windows paths), forward slashes because PHP accepts them and they sidestep the
# escape question entirely, and `''` doubling because an apostrophe would otherwise end the
# string early — `O'Brien` in a path broke the Bash form until the same escape went in.
function ConvertTo-NeonPath($p) {
    "'" + $p.Replace('\', '/').Replace("'", "''") + "'"
}

$PhpstanConfig = ''
if ($env:PHPSTAN_EXPLICIT_CONFIG) {
    $PhpstanConfig = $env:PHPSTAN_EXPLICIT_CONFIG
} else {
    foreach ($candidate in '.phpstan.neon', 'phpstan.neon', '.phpstan.neon.dist',
                           'phpstan.neon.dist', '.phpstan.dist.neon', 'phpstan.dist.neon') {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { $PhpstanConfig = $candidate; break }
    }
}

# Trust gate — before PHPStan is started in any form.
# **This form has not been verified end-to-end**, so on an untrusted diff it stops
# unconditionally rather than imitating the Bash gate's judgement. That is the honest position
# while the reproduction gap stands: a Windows reviewer gets a clear
# `skipped-untrusted-execution` instead of a check whose coverage nobody has measured.
$ExecRisk = @()
if ($env:UNTRUSTED_DIFF -eq '1') {
    $ExecRisk += 'windows-gate-unverified'
    if ($PhpstanConfig) { $ExecRisk += "config-present:$PhpstanConfig" }
    if (Test-Path -LiteralPath 'vendor/composer/autoload_files.php') {
        $ExecRisk += 'composer-autoload-files'
    }
    # A dependency-shipped PHPStan extension activates with nothing in the root config.
    # Match `extra.phpstan.includes`, not a bare `"phpstan"` — the plain string appears in
    # every package that merely *depends* on PHPStan, which would flag most projects.
    $hit = Get-ChildItem -Path 'vendor/*/*/composer.json' -ErrorAction SilentlyContinue |
        Where-Object {
            $j = Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json
            $j.extra -and $j.extra.phpstan -and $j.extra.phpstan.includes
        }
    if ($hit) { $ExecRisk += 'phpstan-extension' }
}

# State line — same reason as the POSIX block: a caller that set neither value would
# otherwise get a normal-looking report with both gates inert.
$readOnlyState = if ($env:READ_ONLY) { $env:READ_ONLY } else { '0' }
$untrustedState = if ($env:UNTRUSTED_DIFF) { $env:UNTRUSTED_DIFF } else { '0' }
"static analysis mode: read-only=$readOnlyState untrusted=$untrustedState"

if ($ExecRisk) {
    "static analysis: skipped-untrusted-execution — analysis would run project code ($($ExecRisk -join ' '))"
} else {
    # Cache isolation. `[System.IO.Path]::GetFullPath` canonicalises `.`/`..` the way
    # `realpath -m` does; `$env:TEMP` is the PowerShell equivalent of TMPDIR and gets the
    # same inside-the-repository check.
    $repoRoot = [System.IO.Path]::GetFullPath((Get-Location).Path)
    $scratch = Join-Path ([System.IO.Path]::GetTempPath()) ("phpstan-review-" + [guid]::NewGuid())
    if ([System.IO.Path]::GetFullPath($scratch).StartsWith($repoRoot, [StringComparison]::OrdinalIgnoreCase)) {
        $scratch = Join-Path 'C:\Windows\Temp' ("phpstan-review-" + [guid]::NewGuid())
    }
    New-Item -ItemType Directory -Path $scratch -Force | Out-Null
    try {
        $override = Join-Path $scratch 'phpstan-review.neon'
        $lines = @()
        if ($PhpstanConfig) {
            $full = [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $PhpstanConfig).Path)
            $lines += 'includes:'
            $lines += '    - ' + (ConvertTo-NeonPath $full)
        }
        $cache = Join-Path $scratch 'cache'
        $lines += 'parameters:'
        $lines += '    tmpDir: ' + (ConvertTo-NeonPath $cache)
        $lines += '    resultCachePath: ' + (ConvertTo-NeonPath (Join-Path $cache 'resultCache.php'))
        if (-not $PhpstanConfig) { $lines += '    level: 5' }
        Set-Content -LiteralPath $override -Value $lines -Encoding UTF8

        & $PhpCmd (Get-Command phpstan).Source analyse $SrcDir `
            --configuration="$override" --no-progress --error-format=raw
    } finally {
        # The config we generate lives in the scratch directory too, so creating it inside
        # the try means a failure between the two never leaves it behind.
        Remove-Item -LiteralPath $scratch -Recurse -Force -ErrorAction SilentlyContinue
    }
}
```

Outside read-only mode, run PHPStan with the project's own configuration exactly as the Bash
block does — the override exists to protect the workspace, not to change the analysis.


### Before analysing an untrusted diff

Analysis itself is static parsing — `paths:` and `scanFiles:` do not run the files. These do,
measured on PHPStan 2.1.42 with PHP 8.3 unless noted:

- `bootstrapFiles:` in the **effective** config — including one declared in a file reached
  through `includes:`, which the root config alone never shows;
- project-defined `rules:` and `services:` — PHPStan instantiates those classes and calls them;
- an `includes:` entry that is a **`.php` file** — PHPStan executes it as dynamic config;
- `composer.json` → `autoload.files`, in the root package **or in any dependency** — declared
  nowhere in `phpstan.neon`. PHPStan loads the composer autoloader, which runs every entry in
  `vendor/composer/autoload_files.php`;
- a PHPStan extension shipped by a dependency, which `phpstan/extension-installer` activates
  through `extra.phpstan.includes` with **nothing in the root config** (documented; not
  reproduced here);
- **any of the above written in NEON's inline or JSON form.** `includes: [danger.php]`,
  `parameters: {bootstrapFiles: [x.php]}`, and a whole-JSON config are all valid and all
  execute (verified). A line-anchored search finds none of them, which is why the gate below
  scans the config as text rather than by line structure;
- on a project pinning **PHPStan before 0.12.26**, the old `autoload_files:` /
  `autoload_directories:` parameters, which *loaded* the files they named. They were replaced by
  `scanFiles:` / `scanDirectories:`, and the replacement is **not a rename**: the current
  parameters only make symbols discoverable to the analyser, they do not execute anything. Read
  the config against the version the project pins;
- the invocation's own `-a` / `--autoload-file`. That flag is yours, not the diff's — but it
  belongs in the closure.

**The check has to run before the analysis, not after it.** The gate above is inside the same
`if`/`elif` chain that launches PHPStan, so a risk found there prevents the run rather than
reporting on one that already happened. For your own or your team's branch it is inert; a hook,
extension, or dependency the diff **adds** is new code whoever wrote it.

**On an untrusted diff the rule is simply "a config at all stops the run."** Reading the config
as text cannot be made sound: NEON's inline forms, an `includes: [inner.neon]` whose target the
block-style chain collector never reaches, and `\uXXXX` escapes that reconstruct `.php` from
text containing no `.php` each defeat it. Proving a config harmless needs a real NEON parser over
the whole include graph, which is not what a shell gate should attempt. So the gate stops, and
the text scan exists only to say **why** in the report. A project with no PHPStan config has no
config-driven execution path and still gets analysed.

---

## 1. CLI Tool Setup

Install all tools as global PHAR binaries. Check existence before installing.

**Read-only:** skip every command in this block; record them as `skipped-read-only`.

```bash
mkdir -p ~/.local/bin

# PHPStan — static analysis (types, bugs, dead code)
if ! command -v phpstan &>/dev/null; then
  wget -q -O ~/.local/bin/phpstan \
    https://github.com/phpstan/phpstan/releases/latest/download/phpstan.phar
  chmod +x ~/.local/bin/phpstan
fi

# phpcs — coding style / PSR compliance
if ! command -v phpcs &>/dev/null; then
  curl -qsL https://phars.phpcodesniffer.com/phpcs.phar -o ~/.local/bin/phpcs
  curl -qsL https://phars.phpcodesniffer.com/phpcbf.phar -o ~/.local/bin/phpcbf
  chmod +x ~/.local/bin/phpcs ~/.local/bin/phpcbf
fi

# phpmd — complexity, dead code, code smells
if ! command -v phpmd &>/dev/null; then
  wget -q -O ~/.local/bin/phpmd \
    https://github.com/phpmd/phpmd/releases/latest/download/phpmd.phar
  chmod +x ~/.local/bin/phpmd
fi

# phpcpd — copy-paste / duplication detection
if ! command -v phpcpd &>/dev/null; then
  wget -q -O ~/.local/bin/phpcpd \
    https://phar.phpunit.de/phpcpd.phar
  chmod +x ~/.local/bin/phpcpd
fi
```

> Install path is `~/.local/bin` (no sudo required). Ensure it is in `$PATH`; `install.sh` handles this automatically.

---

## 2. Running the Tools

Replace `<src>` with the actual source directory (e.g., `src/`, `.`, `app/`).

### PHPStan — static analysis

**§0 ("Using PHP_CMD with tools") owns every PHPStan invocation**, including the explicit
`--configuration` variant. Nothing here repeats a command: a second spelling would drift, and a
bare `phpstan analyse --level=5` would override the level the project deliberately set.

Under a read-only request the cache is **relocated, not judged** — §0 writes an override config
outside the workspace that includes the project's own and redirects both cache keys there. So
there is no "cache path is inside, therefore skip" decision to make any more: the analysis runs,
the findings are the project's own, and the repository is untouched. In normal mode PHPStan uses
the project's cache exactly as before, which is what makes repeat runs fast.

Output: one line per error — `file.php:line:message`. Feed directly into report.

**Level guide**:
| Level | What it checks |
|---|---|
| 0 | Basic syntax, always-false conditions |
| 3 | Unknown methods, wrong argument count |
| 5 | Missing return types, possibly-undefined variables |
| 7 | Union type strictness |
| 9 | Everything; very strict |

### phpcs — coding style
```bash
# Auto-detect standard from phpcs.xml / .phpcs.xml in project root
phpcs --report=full <src>

# Force PSR-12 if no config file
phpcs --standard=PSR12 --report=full <src>

# Machine-readable output for scripting
phpcs --report=json <src>

# Auto-fix what can be fixed
# **Read-only:** skip this command; record it as `skipped-read-only`.
phpcbf --standard=PSR12 <src>
```

### phpmd — complexity & smells
```bash
# All rulesets
phpmd <src> text cleancode,codesize,naming,unusedcode

# Single ruleset
phpmd <src> text codesize

# JSON output
phpmd <src> json cleancode,codesize,naming,unusedcode
```

**Ruleset summary**:
| Ruleset | Catches |
|---|---|
| `cleancode` | Static access, else blocks, boolean args |
| `codesize` | Cyclomatic complexity, long methods, too many params |
| `naming` | Short variables, overly long names |
| `unusedcode` | Unused parameters, local variables, private methods |

### phpcpd — copy-paste detection
```bash
# Default: flags blocks of 5+ duplicate lines
phpcpd <src>

# Lower threshold to catch smaller duplicates
phpcpd --min-lines=3 --min-tokens=30 <src>

# Exclude test directories
phpcpd --exclude=tests <src>
```

---

## 3. Comment Quality

### Flag
```php
// BAD — restates code
$count = count($items); // count items

// BAD — outdated docblock (actual return type differs)
/** @return array */
public function getUser(): ?User { ... }

// BAD — commented-out dead code without reason
// $result = legacyFunction($x);
$result = newFunction($x);
```

### Keep
```php
// GOOD — explains why
// LOCK IN SHARE MODE prevents phantom reads during concurrent batch insert
$stmt = $pdo->prepare('SELECT id FROM orders WHERE status = ? LOCK IN SHARE MODE');

// GOOD — intentional workaround
// PHP < 8.1 lacks readonly properties; using private + getter pattern
private string $token;
```

---

## 4. Style Conventions

Detect project majority first. Flag only genuine deviations.

```php
// BAD — mixed quote style in same file (if project uses single quotes)
$a = 'hello';
$b = "world";   // ← flag this

// BAD — count() in for-loop condition (also a performance issue)
for ($i = 0; $i < count($items); $i++) { }

// BAD — missing type declarations in a typed project
function save($data) { ... }
// vs project pattern:
function save(array $data): bool { ... }
```

---

## 5. Duplication

phpcpd handles structural duplication. Also flag manually:

```php
// BAD — same validation pattern copy-pasted across 3 controllers
if (empty($_POST['email']) || !filter_var($_POST['email'], FILTER_VALIDATE_EMAIL)) {
    return ['error' => 'Invalid email'];
}
// → extract to InputValidator::email($value)

// BAD — near-identical queries differing only in one column
$stmt = $pdo->prepare('SELECT * FROM users WHERE active=1 AND role="admin"');
$stmt = $pdo->prepare('SELECT id FROM users WHERE active=1 AND role="admin"');
// → repository method with column parameter

// BAD — repeated JSON response boilerplate
echo json_encode(['success' => true, 'data' => $result]);
header('Content-Type: application/json');
// → jsonSuccess($data) helper
```

### Grep for duplication patterns
```bash
grep -rn "json_encode.*success" --include="*.php" | sort
grep -rn "filter_var.*FILTER_VALIDATE" --include="*.php"
grep -rn "Content-Type.*application/json" --include="*.php"
```

---

## 6. Performance & Evaluation Order

PHPStan catches type errors but not evaluation order. Flag these manually.

### Guard before expensive operation
```php
// BAD — DB query runs even for invalid input
function getUser(mixed $id): ?User {
    return $this->db->find($id);           // hits DB even if $id is null/0
}

// GOOD — cheap type guard first
function getUser(mixed $id): ?User {
    if (!is_int($id) || $id <= 0) return null;
    return $this->db->find($id);
}
```

### isset / empty before anything
```php
// BAD — strlen() runs even when key is absent
if (strlen($_POST['name']) > 0 && isset($_POST['name'])) { }

// GOOD
if (isset($_POST['name']) && strlen($_POST['name']) > 0) { }
```

### str_contains / str_starts_with before regex
```php
// BAD — full regex engine for a simple prefix check
if (preg_match('/^https?:\/\//', $url)) { }

// GOOD
if (str_starts_with($url, 'http://') || str_starts_with($url, 'https://')) { }
```

### Existence check before full fetch
```php
// BAD — fetches entire row just to test existence
$user = $pdo->query("SELECT * FROM users WHERE email = :email")->fetch();
if ($user) { ... }

// GOOD
$exists = $pdo->prepare("SELECT 1 FROM users WHERE email = :email LIMIT 1");
$exists->execute([':email' => $email]);
if ($exists->fetchColumn()) { ... }
```

### N+1 query
```php
// BAD — N queries inside loop
$orders = $pdo->query("SELECT * FROM orders")->fetchAll();
foreach ($orders as $order) {
    $order['user'] = getUserById($order['user_id']);  // 1 query per row
}

// GOOD — 2 queries total
$userIds = array_column($orders, 'user_id');
$placeholders = implode(',', array_fill(0, count($userIds), '?'));
$users = $pdo->prepare("SELECT * FROM users WHERE id IN ($placeholders)")
             ->execute($userIds)->fetchAll();
$usersById = array_column($users, null, 'id');
```

### Loop invariants
```php
// BAD
for ($i = 0; $i < count($items); $i++) { }

// GOOD
$total = count($items);
for ($i = 0; $i < $total; $i++) { }
```

### array_flip for O(1) lookup
```php
// BAD — O(n) per iteration
foreach ($items as $item) {
    if (in_array($item->id, $largeArray)) { ... }
}

// GOOD — build hash map once, O(1) lookup
$lookup = array_flip($largeArray);
foreach ($items as $item) {
    if (isset($lookup[$item->id])) { ... }
}
```

### Grep patterns
```bash
grep -rn "for.*count(" --include="*.php"                    # loop invariant
grep -rn "SELECT \*" --include="*.php"                       # over-fetching
grep -rn "->fetch\b" --include="*.php" -A3 | grep "if ("    # fetch-then-existence
grep -rn "in_array" --include="*.php"                        # potential O(n) lookup
```
