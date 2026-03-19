# PHP Code Quality Reference

CLI tools and manual patterns for PHP quality review.

## Table of Contents
1. [CLI Tool Setup](#1-cli-tool-setup)
2. [Running the Tools](#2-running-the-tools)
3. [Comment Quality](#3-comment-quality)
4. [Style Conventions](#4-style-conventions)
5. [Duplication](#5-duplication)
6. [Performance & Evaluation Order](#6-performance--evaluation-order)

---

## 1. CLI Tool Setup

Install all tools as global PHAR binaries. Check existence before installing.

```bash
# PHPStan — static analysis (types, bugs, dead code)
if ! command -v phpstan &>/dev/null; then
  wget -q -O /usr/local/bin/phpstan \
    https://github.com/phpstan/phpstan/releases/latest/download/phpstan.phar
  chmod +x /usr/local/bin/phpstan
fi

# phpcs — coding style / PSR compliance
if ! command -v phpcs &>/dev/null; then
  curl -qsL https://phars.phpcodesniffer.com/phpcs.phar -o /usr/local/bin/phpcs
  curl -qsL https://phars.phpcodesniffer.com/phpcbf.phar -o /usr/local/bin/phpcbf
  chmod +x /usr/local/bin/phpcs /usr/local/bin/phpcbf
fi

# phpmd — complexity, dead code, code smells
if ! command -v phpmd &>/dev/null; then
  wget -q -O /usr/local/bin/phpmd \
    https://static.phpmd.org/php/latest/phpmd.phar
  chmod +x /usr/local/bin/phpmd
fi

# phpcpd — copy-paste / duplication detection
if ! command -v phpcpd &>/dev/null; then
  wget -q -O /usr/local/bin/phpcpd \
    https://phar.phpunit.de/phpcpd.phar
  chmod +x /usr/local/bin/phpcpd
fi
```

> If `sudo` is unavailable, install to `~/bin/` and ensure it is in `$PATH`.

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
