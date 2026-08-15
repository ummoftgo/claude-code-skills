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

PHPStan auto-discovers **three** config names — `phpstan.neon`, `phpstan.neon.dist`, and
`phpstan.dist.neon`. Checking only the first two makes a project that ships just
`phpstan.dist.neon` look unconfigured, and the `--level=5` fallback then overrides the level the
project actually set.

**Check the cache location before running under a read-only request.** PHPStan writes its result
cache to `sys_get_temp_dir()/phpstan` by default — outside the repository, so the default is
safe. Two settings can move it inside:

- `tmpDir` — a **relative** value resolves against the config file's directory;
- `resultCachePath` — sets the cache file directly, **independently of `tmpDir`**, so checking
  `tmpDir` alone misses it.

Read **the config actually in effect**, not just the root auto-discovered names, and follow
`includes:` **all the way down** — a grandparent config can set the cache path, and each include
list resolves against the directory of the file that declares it.

```bash
# One variable decides everything below: which config PHPStan will actually use.
# Resolve it in PHPStan's own priority order — NOT with `ls | head -1`, which sorts
# alphabetically and would pick phpstan.dist.neon over phpstan.neon.
PHPSTAN_CONFIG=""
if [ -n "${PHPSTAN_EXPLICIT_CONFIG:-}" ]; then
  PHPSTAN_CONFIG="$PHPSTAN_EXPLICIT_CONFIG"          # set only when the run passes --configuration
else
  for candidate in phpstan.neon phpstan.neon.dist phpstan.dist.neon; do
    [ -f "$candidate" ] && { PHPSTAN_CONFIG="$candidate"; break; }
  done
fi

# Read-only gate. Decide first, then run — printing the grep result and running anyway is
# not a gate. `CACHE_RISK` non-empty means the cache would land inside the repository, or we
# could not tell.
CONFIG_CHAIN=""
CACHE_RISK=""

# Walk `includes:` **recursively**. One level is not enough: a grandparent config can set the
# cache path, and stopping at the parent lets it through. Paths inside an include list resolve
# against the including file's directory, not the working directory.
collect_config() {
  local file="$1" dir inc target canonical
  if [ ! -r "$file" ]; then
    CACHE_RISK="config unreadable: $file"      # cannot judge → not safe
    return
  fi
  # Compare canonical paths: `phpstan.neon`, `./phpstan.neon`, and `././phpstan.neon` are the
  # same file, and a raw string compare would recurse forever on a self-include.
  canonical=$(cd "$(dirname "$file")" 2>/dev/null && printf '%s/%s' "$(pwd)" "$(basename "$file")") \
    || { CACHE_RISK="unresolvable: $file"; return; }
  # Newline-separated, not space-separated: a project path containing a space would otherwise
  # split into fragments and every config would look unresolvable, skipping analysis for good
  # projects. Windows paths (`C:\Users\First Last\...`) hit this immediately.
  case "$(printf '%s\n' "$CONFIG_CHAIN")" in *"$canonical"$'\n'*) return ;; esac
  CONFIG_CHAIN="$CONFIG_CHAIN$canonical"$'\n'
  dir=$(dirname "$file")
  while IFS= read -r inc; do
    inc=$(printf '%s' "$inc" | sed "s/^[[:space:]]*-[[:space:]]*//; s/[\"']//g")
    [ -n "$inc" ] || continue
    case "$inc" in /*) target="$inc" ;; *) target="$dir/$inc" ;; esac
    collect_config "$target"
  done < <(awk '/^includes:/{f=1;next} f&&/^[[:space:]]*-/{print} f&&/^[^[:space:]-]/{f=0}' "$file")
}

if [ -n "$PHPSTAN_CONFIG" ]; then
  collect_config "$PHPSTAN_CONFIG"
  # Judge each cache setting against the directory of the file that declares it.
  while IFS= read -r cfg; do
    [ -n "$cfg" ] || continue
    cfg_dir=$(cd "$(dirname "$cfg")" 2>/dev/null && pwd) || { CACHE_RISK="unresolvable: $cfg"; continue; }
    while IFS= read -r setting; do
      value=$(printf '%s' "${setting#*:}" | tr -d " \"'")
      [ -n "$value" ] || continue
      case "$value" in /*) resolved="$value" ;; *) resolved="$cfg_dir/$value" ;; esac
      case "$resolved" in "$PWD"|"$PWD"/*) CACHE_RISK="$cfg: $setting" ;; esac
    done < <(grep -hE '^[[:space:]]*(tmpDir|resultCachePath):' "$cfg" 2>/dev/null)
  done <<< "$CONFIG_CHAIN"
fi
# No config at all is safe: PHPStan then uses sys_get_temp_dir()/phpstan, outside the repository.

# Trust gate — decided BEFORE the analysis runs, using the chain collected above.
# Set UNTRUSTED_DIFF=1 for a branch you would not execute (outside contributor, unfamiliar
# dependency). On a trusted branch this whole block is inert and nothing changes.
EXEC_RISK=""
if [ "${UNTRUSTED_DIFF:-0}" = "1" ]; then
  while IFS= read -r cfg; do
    [ -n "$cfg" ] || continue
    case "$cfg" in *.php) EXEC_RISK="$EXEC_RISK executable-config:$cfg" ;; esac
    grep -qE '^[[:space:]]*(bootstrapFiles|rules|services):' "$cfg" 2>/dev/null &&
      EXEC_RISK="$EXEC_RISK config-loads-code:$cfg"
    # Older PHPStan (before 0.12.26) loaded files through these; a project pinning such a
    # version still executes them, so check both spellings rather than the current one only.
    grep -qE '^[[:space:]]*(autoload_files|autoload_directories):' "$cfg" 2>/dev/null &&
      EXEC_RISK="$EXEC_RISK legacy-autoload:$cfg"
  done <<< "$CONFIG_CHAIN"
  # Composer runs every entry here, including dependencies' own `autoload.files`.
  # No `head`: a truncated list reads as a short list, and the entry that matters may be last.
  if [ -f vendor/composer/autoload_files.php ] &&
     grep -qE "=> .*'" vendor/composer/autoload_files.php; then
    EXEC_RISK="$EXEC_RISK composer-autoload-files"
  fi
  # Dependency-shipped extensions, auto-activated by phpstan/extension-installer.
  if grep -rlE '"phpstan"' vendor/*/*/composer.json 2>/dev/null |
     xargs -r grep -lE '"includes"' 2>/dev/null | grep -q .; then
    EXEC_RISK="$EXEC_RISK phpstan-extension"
  fi
fi

# PHPStan — run under the correct PHP binary, using the config resolved above
if [ -n "$EXEC_RISK" ]; then
  echo "static analysis: skipped-untrusted-execution — analysis would run project code ($EXEC_RISK)"
elif [ "${READ_ONLY:-0}" = "1" ] && [ -n "$CACHE_RISK" ]; then
  echo "static analysis: skipped-read-only — result cache would be written inside the repository ($CACHE_RISK)"
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

If either setting resolves inside the repository — or the effective config cannot be determined —
do not run the analysis under a read-only request. Record static analysis as `skipped-read-only`
and say it needs write permission or a cache path outside the repository. **Unknown is not safe**:
a config that could not be read is exactly the case where a write would be a surprise. In normal
mode the cache write is expected and desirable.

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
