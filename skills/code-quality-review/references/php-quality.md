# PHP Code Quality Reference

CLI tools and manual patterns for PHP quality review.

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

### Using PHP_CMD with tools

Only **PHPStan** uses the PHP binary for type analysis — the others are version-agnostic style checkers.

```bash
# PHPStan — run under the correct PHP binary
$PHP_CMD $(command -v phpstan) analyse <src> --no-progress --error-format=raw

# phpcs / phpmd / phpcpd — version-agnostic; default php is fine
phpcs --report=full <src>
phpmd <src> text cleancode,codesize,naming,unusedcode
phpcpd <src>
```

---

## 1. CLI Tool Setup

Install all tools as global PHAR binaries. Check existence before installing.

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
    https://static.phpmd.org/php/latest/phpmd.phar
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
```bash
# Level 5 is a good balance; raise to 8 for strict projects
phpstan analyse <src> --level=5 --no-progress --error-format=raw

# If phpstan.neon exists in the project root, it is picked up automatically
# To use a specific config:
phpstan analyse --configuration=phpstan.neon
```

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
