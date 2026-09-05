# Cross-validation patterns

Read only for an existing Critical/High finding whose evidence needs a targeted pattern check. Select the implicated language and platform; run only relevant commands against the implicated files. A match locates a candidate; confirm reachability and impact in context. A non-match never proves safety.

**Security patterns** (from `web-security-review/references/`):
```bash
# Use -P for Perl-compatible regex (\s, alternation groups) — required on GNU grep

# SQL injection
grep -rnP "query\s*\(\s*[\"'].*\$" --include="*.php" <implicated_files>
grep -rnP "\.\s*\$_(GET|POST|REQUEST|COOKIE)" --include="*.php" <implicated_files>

# XSS
grep -rnP "echo \$_(GET|POST|REQUEST|COOKIE|SERVER)" --include="*.php" <implicated_files>
grep -rnP "innerHTML\s*=" --include="*.js" --include="*.svelte" <implicated_files>

# CSRF — check for missing token validation on state-changing endpoints
grep -rn "\$_POST\[" --include="*.php" <implicated_files> | grep -iv "csrf"

# Session security
grep -rn "session_start" --include="*.php" <implicated_files>
grep -rn "session_regenerate_id" --include="*.php" <implicated_files>

# File upload
grep -rnP "move_uploaded_file|\\\$_FILES" --include="*.php" <implicated_files>

# Hardcoded secrets
grep -rnP "password\s*=\s*['\"][^'\"]{3,}" --include="*.php" --include="*.js" <implicated_files>
grep -rnP "api_key|secret_key|access_token" --include="*.env" --include="*.json" <implicated_files>

# Frontend sinks
grep -rnP "\.html\(|\.append\(|\.prepend\(" --include="*.js" <implicated_files>
grep -rn "{@html" --include="*.svelte" <implicated_files>
grep -rnP "localStorage|sessionStorage" --include="*.js" --include="*.svelte" <implicated_files>

# Python — injection sinks, unsafe deserialization, template escape hatches, weak randomness
grep -rnP 'execute\(f["'"'"']|execute\(.*%\s*\(|\.raw\(|\.extra\(' --include="*.py" <implicated_files>
grep -rnP "shell\s*=\s*True|os\.system|os\.popen" --include="*.py" <implicated_files>
grep -rnP "pickle\.loads?|yaml\.load\(|\beval\(|\bexec\(" --include="*.py" <implicated_files>
grep -rnP "mark_safe|\|safe|Markup\(|Template\(" --include="*.py" <implicated_files>
grep -rnP "random\.(choice|randint|choices)|md5\(|sha1\(|verify\s*=\s*False" --include="*.py" <implicated_files>

# Go — shell re-entry, formatted SQL, the wrong template package, weak randomness
grep -rnP 'exec\.Command\("(sh|bash|cmd|powershell)"' --include="*.go" <implicated_files>
grep -rnP "(Query|Exec|QueryRow)\w*\(\s*fmt\.Sprintf" --include="*.go" <implicated_files>
grep -rn '"text/template"' --include="*.go" <implicated_files>
grep -rnP "math/rand|InsecureSkipVerify|crypto/(md5|sha1)" --include="*.go" <implicated_files>

# Rust — reachable panics, formatted SQL, shell re-entry, unsafe, TLS bypass
grep -rnP "\.unwrap\(\)|\.expect\(" --include="*.rs" <implicated_files>
grep -rnP "query\(&?format!|sql_query\(|execute\(&?format!" --include="*.rs" <implicated_files>
grep -rnP 'Command::new\("(sh|bash|cmd|powershell)"' --include="*.rs" <implicated_files>
grep -rnP "unsafe\s*\{|from_raw_parts|get_unchecked|transmute" --include="*.rs" <implicated_files>
grep -rnP "danger_accept_invalid_certs|SmallRng|seed_from_u64" --include="*.rs" <implicated_files>
```

`.unwrap()` in Rust is the one pattern here that matches far more than it should — it is
idiomatic in `main`, tests, and benches. Use it to locate the flagged line, never as
corroboration on its own.

**Quality patterns** (from `code-quality-review/references/`):
```bash
# N+1 / query inside loop (use as signal; confirm manually — 3-line window misses service calls)
grep -rn "foreach\|for " --include="*.php" -A3 <implicated_files> | grep -i "query\|prepare\|execute"
grep -rn "for.*count(" --include="*.php" <implicated_files>
grep -rn "SELECT \*" --include="*.php" <implicated_files>

# Manual Svelte subscribe without cleanup
grep -rn "\.subscribe(" --include="*.svelte" <implicated_files>

# Python / Go / Rust quality signals (confirm manually — a window match is not a finding)
grep -rnP "except\s*:|except Exception" --include="*.py" <implicated_files>
grep -rnP "def \w+\([^)]*=\s*(\[\]|\{\})" --include="*.py" <implicated_files>
grep -rn "for " --include="*.go" -A3 <implicated_files> | grep -P "defer |\.Query\(|http\.Get"
grep -rnP ":?=\s*_\s*,|,\s*_\s*:?=" --include="*.go" <implicated_files>
grep -rnP "std::(fs|thread::sleep)|\.lock\(\)" --include="*.rs" <implicated_files>

# CSS issues
grep -rn "!important" --include="*.css" --include="*.scss" <implicated_files>
```

On native Windows, cross-validate only the implicated files with `rg` or this PowerShell fallback; do not scan the whole repository:

```powershell
$implicatedFiles = @('path\to\flagged-file.php', 'src\Flagged.svelte')
$patternFamilies = [ordered]@{
  SqlInjection = @('query\s*\(\s*["''].*\$', '\.\s*\$_(?:GET|POST|REQUEST|COOKIE)')
  Xss = @('echo\s+\$_(?:GET|POST|REQUEST|COOKIE|SERVER)', 'innerHTML\s*=', '\.html\(', '\.append\(', '\.prepend\(', '\{@html')
  Csrf = @('\$_POST\[') # manually confirm that no CSRF validation protects the endpoint
  Session = @('session_start', 'session_regenerate_id')
  Upload = @('move_uploaded_file', '\$_FILES')
  Secrets = @('password\s*=\s*["''][^"'']{3,}', 'api_key', 'secret_key', 'access_token')
  BrowserStorage = @('localStorage', 'sessionStorage')
  BackendQuality = @('foreach', 'for\s*\(', 'query', 'prepare', 'execute', 'for.*count\(', 'SELECT\s+\*')
  FrontendQuality = @('\.subscribe\(', '!important')
  PythonSecurity = @('execute\(f["'']', '\.raw\(', '\.extra\(', 'shell\s*=\s*True', 'os\.system', 'os\.popen', 'pickle\.loads?', 'yaml\.load\(', 'mark_safe', 'Markup\(', 'random\.(?:choice|randint|choices)', 'verify\s*=\s*False')
  GoSecurity = @('exec\.Command\("(?:sh|bash|cmd|powershell)"', '(?:Query|Exec|QueryRow)\w*\(\s*fmt\.Sprintf', '"text/template"', 'math/rand', 'InsecureSkipVerify')
  RustSecurity = @('\.unwrap\(\)', '\.expect\(', 'query\(&?format!', 'sql_query\(', 'Command::new\("(?:sh|bash|cmd|powershell)"', 'unsafe\s*\{', 'from_raw_parts', 'get_unchecked', 'transmute', 'danger_accept_invalid_certs')
  PythonQuality = @('except\s*:', 'except Exception', 'def \w+\([^)]*=\s*(?:\[\]|\{\})')
  GoQuality = @('defer ', ':?=\s*_\s*,', ',\s*_\s*:?=')
  RustQuality = @('std::fs', 'std::thread::sleep', '\.lock\(\)')
}
$files = Get-ChildItem -LiteralPath $implicatedFiles -File -ErrorAction SilentlyContinue
foreach ($family in $patternFamilies.GetEnumerator()) {
  $files | Select-String -Pattern $family.Value -CaseSensitive:$false |
    ForEach-Object { '[{0}] {1}:{2}: {3}' -f $family.Key, $_.Path, $_.LineNumber, $_.Line.Trim() }
}
```
