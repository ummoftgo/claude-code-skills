# PHP Backend Security Reference

Security checklist for PHP web applications. Used by the `web-security-review` skill.

## Table of Contents
1. [SQL Injection](#1-sql-injection)
2. [XSS — Output Encoding](#2-xss--output-encoding)
3. [CSRF Protection](#3-csrf-protection)
4. [Session Security](#4-session-security)
5. [File Upload Security](#5-file-upload-security)
6. [Authentication & Password Handling](#6-authentication--password-handling)
7. [Input Validation](#7-input-validation)
8. [Directory Traversal](#8-directory-traversal)
9. [Error & Exception Handling](#9-error--exception-handling)
10. [Miscellaneous](#10-miscellaneous)

---

## 1. SQL Injection

**Severity if violated**: Critical

### MUST
- MUST use PDO or MySQLi prepared statements for ALL queries that include any variable data.
- MUST use named or positional placeholders; NEVER concatenate variables into SQL strings.
- MUST set `PDO::ATTR_EMULATE_PREPARES => false` so the DB driver enforces real parameterization.

### Secure pattern
```php
// GOOD
$stmt = $pdo->prepare('SELECT * FROM users WHERE email = :email AND active = 1');
$stmt->execute([':email' => $email]);

// BAD — SQL injection
$result = $pdo->query("SELECT * FROM users WHERE email = '$email'");
```

### Audit grep patterns
```bash
grep -rn "query\s*(\s*[\"'].*\$" --include="*.php"
grep -rn "\.\s*\$_(GET|POST|REQUEST|COOKIE)" --include="*.php"
```

---

## 2. XSS — Output Encoding

**Severity if violated**: High

### MUST
- MUST encode ALL user-controlled values before inserting into HTML using `htmlspecialchars($val, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8')`.
- MUST use the correct encoding context: HTML body, HTML attribute, JavaScript, URL — each requires different encoding.
- MUST NOT echo raw `$_GET`, `$_POST`, `$_COOKIE`, `$_SERVER['HTTP_*']`, or database-stored user content.

### Secure pattern
```php
// GOOD — HTML context
echo htmlspecialchars($user['display_name'], ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');

// GOOD — URL context
echo urlencode($search_term);

// BAD
echo $_GET['name'];
echo $row['comment']; // stored user content, unencoded
```

### Audit grep patterns
```bash
grep -rn "echo \$_(GET|POST|REQUEST|COOKIE|SERVER)" --include="*.php"
grep -rn "print \$_(GET|POST)" --include="*.php"
```

---

## 3. CSRF Protection

**Severity if violated**: High

### MUST
- MUST generate a random, per-session CSRF token on session start.
- MUST validate the token for every state-changing request (POST, PUT, DELETE, PATCH).
- MUST use `hash_equals()` for token comparison (timing-safe).
- MUST regenerate the token after successful validation for high-risk actions (password change, etc.).

### Secure pattern
```php
// Generate
if (empty($_SESSION['csrf_token'])) {
    $_SESSION['csrf_token'] = bin2hex(random_bytes(32));
}

// Embed in form
echo '<input type="hidden" name="csrf_token" value="'
    . htmlspecialchars($_SESSION['csrf_token'], ENT_QUOTES, 'UTF-8') . '">';

// Validate
if (!hash_equals($_SESSION['csrf_token'], $_POST['csrf_token'] ?? '')) {
    http_response_code(403);
    exit('CSRF validation failed');
}
```

### Audit grep patterns
```bash
# Find POST handlers that may be missing csrf check
grep -rn "\$_POST\[" --include="*.php" | grep -v "csrf"
```

---

## 4. Session Security

**Severity if violated**: High

### MUST
- MUST call `session_regenerate_id(true)` immediately after login to prevent session fixation.
- MUST set `session.cookie_httponly = 1` (prevents JS access to session cookie).
- MUST set `session.cookie_samesite = Strict` (or `Lax` minimum).
- MUST set `session.cookie_secure = 1` when running over HTTPS.
- MUST NOT store sensitive data (plaintext passwords, payment info) in `$_SESSION`.
- SHOULD set a reasonable `session.gc_maxlifetime` (e.g., 3600 for 1 hour idle timeout).

### Secure pattern
```php
// Recommended session config (before session_start)
ini_set('session.cookie_httponly', 1);
ini_set('session.cookie_samesite', 'Strict');
ini_set('session.use_strict_mode', 1);
session_start();

// After successful login:
session_regenerate_id(true);
$_SESSION['user_id'] = $user['id'];
```

### Audit grep patterns
```bash
grep -rn "session_start" --include="*.php"         # check config around each call
grep -rn "session_regenerate_id" --include="*.php" # should exist in login handler
```

---

## 5. File Upload Security

**Severity if violated**: Critical (arbitrary code execution) / High

### MUST
- MUST validate MIME type server-side using `finfo_file()` — NEVER trust `$_FILES['file']['type']` (client-controlled).
- MUST use an allowlist of permitted extensions (e.g., `['jpg','png','pdf']`), not a blocklist.
- MUST rename uploaded files to a random name (e.g., `bin2hex(random_bytes(16)) . '.jpg'`).
- MUST store uploaded files outside the web root, or in a directory with PHP execution disabled.
- MUST set a maximum file size in both PHP config and application logic.
- MUST NOT allow user-controlled paths when calling `move_uploaded_file()`.

### Secure pattern
```php
$allowed_types = ['image/jpeg', 'image/png', 'image/gif'];
$finfo = finfo_open(FILEINFO_MIME_TYPE);
$mime = finfo_file($finfo, $_FILES['upload']['tmp_name']);
finfo_close($finfo);

if (!in_array($mime, $allowed_types, true)) {
    throw new \RuntimeException('Invalid file type');
}

$safe_name = bin2hex(random_bytes(16)) . '.jpg';
$dest = '/var/uploads/' . $safe_name; // outside web root
move_uploaded_file($_FILES['upload']['tmp_name'], $dest);
```

### Audit grep patterns
```bash
grep -rn "move_uploaded_file" --include="*.php"
grep -rn "\$_FILES" --include="*.php"
```

---

## 6. Authentication & Password Handling

**Severity if violated**: Critical

### MUST
- MUST hash passwords with `password_hash($password, PASSWORD_BCRYPT)` or `PASSWORD_ARGON2ID`.
- MUST verify with `password_verify($input, $hash)` — never compare hashes with `==` or `===`.
- MUST NOT store plaintext or MD5/SHA1-hashed passwords.
- MUST limit login attempts (rate limiting or account lockout after N failures).
- MUST use `random_bytes(32)` for password reset tokens, store hashed, expire after 1 hour.

### Secure pattern
```php
// Registration
$hash = password_hash($plaintext_password, PASSWORD_BCRYPT, ['cost' => 12]);

// Login
if (!password_verify($submitted_password, $stored_hash)) {
    // increment failure counter
    http_response_code(401);
    exit('Invalid credentials');
}
```

### Audit grep patterns
```bash
grep -rn "md5\|sha1\b" --include="*.php" | grep -i "pass"
grep -rn "password_hash\|password_verify" --include="*.php"
```

---

## 7. Input Validation

**Severity if violated**: Medium–High depending on context

### MUST
- MUST validate type, format, length, and range for all user inputs at the server boundary.
- MUST use a whitelist approach: define what is valid, reject everything else.
- MUST use `filter_var()` for common formats (email, URL, int, float).
- MUST validate even inputs from hidden form fields or cookies.

### Secure pattern
```php
// Email
$email = filter_var($_POST['email'] ?? '', FILTER_VALIDATE_EMAIL);
if ($email === false) { /* reject */ }

// Integer in range
$page = filter_var($_GET['page'] ?? 1, FILTER_VALIDATE_INT, [
    'options' => ['min_range' => 1, 'max_range' => 1000]
]);
if ($page === false) { $page = 1; }

// Whitelist for enum-like values
$status = $_POST['status'] ?? '';
if (!in_array($status, ['active', 'inactive', 'pending'], true)) { /* reject */ }
```

---

## 8. Directory Traversal

**Severity if violated**: Critical

### MUST
- MUST NEVER use user input directly as a filesystem path or filename.
- MUST use `basename()` to strip directory components, then validate against an allowlist or known safe directory.
- MUST use `realpath()` to resolve the final path and verify it starts with the expected base directory.

### Secure pattern
```php
$base_dir = realpath('/var/app/uploads/');
$requested = basename($_GET['file'] ?? '');
$full_path = realpath($base_dir . '/' . $requested);

if ($full_path === false || strpos($full_path, $base_dir) !== 0) {
    http_response_code(403);
    exit('Access denied');
}
```

### Audit grep patterns
```bash
grep -rn "include\s*(\s*\$\|.*\$_(GET|POST)" --include="*.php"
grep -rn "file_get_contents\s*(\s*\$" --include="*.php"
grep -rn "readfile\s*(\s*\$" --include="*.php"
```

---

## 9. Error & Exception Handling

**Severity if violated**: Medium (information disclosure)

### MUST
- MUST set `display_errors = Off` in production (`ini_set('display_errors', 0)`).
- MUST log errors to a file (`log_errors = On`) rather than displaying them.
- MUST return generic error messages to the client; never expose stack traces, file paths, SQL queries, or internal state.
- MUST wrap database and external service calls in try/catch and handle exceptions gracefully.

### Secure pattern
```php
ini_set('display_errors', 0);
ini_set('log_errors', 1);

try {
    $result = $pdo->query($sql);
} catch (\PDOException $e) {
    error_log('DB error: ' . $e->getMessage());
    http_response_code(500);
    echo json_encode(['success' => false, 'error' => 'Internal server error']);
    exit;
}
```

### Audit grep patterns
```bash
grep -rn "display_errors.*[Oo]n\|display_errors.*,.*1" --include="*.php"
grep -rn "echo.*getMessage\|print.*exception" --include="*.php"
```

---

## 10. Miscellaneous

### HTTP Security Headers (Medium)
Send these security headers from PHP:
```php
header('X-Content-Type-Options: nosniff');
header('X-Frame-Options: DENY');
header('Referrer-Policy: strict-origin-when-cross-origin');
// Content-Security-Policy: set based on actual script/style sources
```

### CORS (High if misconfigured)
- MUST NOT set `Access-Control-Allow-Origin: *` for authenticated endpoints.
- MUST validate `$_SERVER['HTTP_ORIGIN']` against a strict allowlist before reflecting it.

```php
$allowed_origins = ['https://app.example.com'];
$origin = $_SERVER['HTTP_ORIGIN'] ?? '';
if (in_array($origin, $allowed_origins, true)) {
    header('Access-Control-Allow-Origin: ' . $origin);
}
```

### Sensitive Data Exposure (High)
- MUST NOT log passwords, session tokens, or payment card data.
- MUST NOT return more data than needed in API responses (avoid returning full user rows).
- MUST store secrets (API keys, DB credentials) in environment variables, not in source code.

```bash
# Audit for hardcoded secrets
grep -rn "password\s*=\s*['\"][^'\"]\+['\"]" --include="*.php"
grep -rn "api_key\s*=\s*['\"]" --include="*.php"
```
