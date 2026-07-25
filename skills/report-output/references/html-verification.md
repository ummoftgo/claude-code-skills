# HTML Report Verification — CSP Hash and Self-Containment Scan

Concrete commands for SKILL.md Step 3B items 2–3. Everything here runs against the **temp candidate** (`$tmp` from the atomic-publish rule), never the final path.

## 1. Recompute the CSP script hash

If you changed the inline `<script>` relative to the template (you almost always do when customizing), recompute the CSP hash and update `script-src 'sha256-…'` in the CSP meta tag — otherwise the report's own script will not run. Use whichever calculator exists on the machine (check with `command -v` / `Get-Command` first).

node (any platform):
```bash
node -e "const fs=require('fs'),c=require('crypto');const m=fs.readFileSync(process.argv[1],'utf8').match(/<script>([\s\S]*?)<\/script>/);console.log('sha256-'+c.createHash('sha256').update(m[1].replace(/\r\n?/g,'\n')).digest('base64'))" "$tmp"
```

python3 (POSIX fallback):
```bash
python3 -c "import re,sys,hashlib,base64;h=open(sys.argv[1],encoding='utf-8').read();m=re.search(r'<script>(.*?)</script>',h,re.S);s=re.sub(r'\r\n?','\n',m.group(1));print('sha256-'+base64.b64encode(hashlib.sha256(s.encode()).digest()).decode())" "$tmp"
```

Windows PowerShell 5.1+ (.NET, no external tools):
```powershell
$html = Get-Content -Raw -Encoding UTF8 -LiteralPath $tmp
$s = [regex]::Match($html, '(?s)<script>(.*?)</script>').Groups[1].Value -replace "`r`n?", "`n"
$sha = [System.Security.Cryptography.SHA256]::Create()
'sha256-' + [Convert]::ToBase64String($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($s)))
```

The hash covers the exact text between `<script>` and `</script>` — recompute after any script edit, however small. The `\r\n → \n` normalization is mandatory: HTML parsers normalize newlines to LF *before* the browser hashes the script, so hashing raw CRLF bytes (typical on Windows) produces a value the browser will never match. With the normalization, LF and CRLF copies of the same file yield the same hash.

**Fail closed**: if no calculator is available, do not deliver an HTML file whose script differs from the shipped template — a stale hash silently disables the report's own features. Either keep the template `<script>` byte-identical (its shipped hash stays valid) or deliver the Markdown report instead, and say which constraint applied.

## 2. Self-containment scan (triage)

The scan is **triage only** — it lists every candidate external reference; the browser check in Step 3B item 4 is the authoritative gate. HTML element/attribute names are case-insensitive, so the scan must be too.

POSIX (`rg -in`; if unavailable, `grep -inE` with the same pattern):
```bash
rg -in "(src|href|srcset|poster|action|formaction)\s*=|<(object|embed|iframe|form|base)\b|http-equiv\s*=\s*[\"']?refresh|url\(|@import|fetch\(|XMLHttpRequest|WebSocket|sendBeacon|EventSource|import\(" "$tmp"
```

Windows PowerShell (`Select-String` is case-insensitive by default — do not pass `-CaseSensitive`):
```powershell
Select-String -LiteralPath $tmp -Pattern '(src|href|srcset|poster|action|formaction)\s*=|<(object|embed|iframe|form|base)\b|http-equiv\s*=\s*["'']?refresh|url\(|@import|fetch\(|XMLHttpRequest|WebSocket|sendBeacon|EventSource|import\('
```

Classify each match by its **context in the source** — the raw match count decides nothing:

- **Blocker** — the match is live: inside a tag token (`<img src=…>`, `<form action=…>`), inside the report's inline `<script>` or `<style>`, or in active CSS (`url(`, `@import`). Only three live forms are allowed: `href="#…"` anchors, visible documentation links (`<a href="https://…">` in body text), and `data:` URIs. Protocol-relative `//host` URLs are never allowed.
- **Safe** — the match is escaped report content in visible text (evidence inside `<pre><code>`, quoted output in prose): at that position markup characters appear as entities (`&lt;img src=…&gt;`) or the token is plain text in a text node (`fetch(` in a code sample). That is data, not instructions — **never delete evidence just to silence the scan**. A security or code-review report will legitimately match `fetch(`, `href=`, `url(` in its evidence.

Also confirm the temp candidate keeps `<meta charset="utf-8">` and the CSP meta tag (with a current script hash), and is under ~500 KB.
