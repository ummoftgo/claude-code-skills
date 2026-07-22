---
name: report-output
description: "Format and deliver a user-requested report (review findings, analysis results, research summaries, status/incident reports). Trigger when the user asks for a report output — '리포트로 만들어줘', '보고서로 출력해줘', '리포트 출력해줘', '결과를 보고서로 정리해줘', 'output as a report', 'write this up as a report' — or when another skill has produced results the user wants delivered as a report. First asks the user whether to emit Markdown or HTML (skips the question when the format is already specified), then applies the matching format: Markdown conventions for archival/agent-readable reports, or the researched self-contained single-file HTML format in references/html-report-format.md for human-readable rich reports."
---

# Report Output

Deliver report-shaped output in the format that fits its purpose. Markdown wins the archive (version control, diffs, search, agent re-ingestion); HTML wins the session (human reading, visual structure, sharing). Ask which one the user wants, then apply the matching format rules.

> **Scope**: This skill governs *how a report is formatted and delivered*. It does not gather findings itself — the report content comes from the current conversation, another skill's output (e.g., `branch-merge-review`, `web-security-review`), or files the user points at.

> **Read-only mode (priority rule)**: If the user asked not to write anything ("수정하지 말고", "read-only", or a read-only sandbox), do not create report files. Emit the report inline as Markdown and state that HTML delivery requires file writes.

---

## Step 1: Decide the format

**Skip the question** when the format is already determined:
- The user named a format ("HTML 리포트로", "md로 정리해줘") → use it.
- The invoking skill mandates a format (e.g., `branch-merge-review` Step 5 specifies a `.md` report) → follow that skill; only offer an HTML companion if the user asks.

Otherwise **ask the user** before writing anything. In Claude Code use `AskUserQuestion`; in other agents ask in plain text. Present both options with their real trade-offs, and recommend one based on the content:

| Signal in the report content | Recommend |
|---|---|
| Will be committed, diffed, searched, or re-read by agents later (spec, plan, changelog) | **Markdown** |
| Short (< ~100 lines), simple prose, terminal-bound | **Markdown** |
| Long or dense: many findings, severity grades, comparisons, tables, diagrams | **HTML** |
| Will be shared with teammates who won't open a code editor | **HTML** |
| Needs visual evidence: diffs, flows, charts, before/after, spatial layout | **HTML** |

Question shape (translate to the user's language):
- **Markdown** — 버전 관리·검색·에이전트 재사용에 유리, 토큰 효율적. 아카이브용.
- **HTML** — 시각적 구조·색상·다이어그램으로 읽기 쉬움, 브라우저로 열어 공유하기 좋음. 사람이 읽는 용도.

Both formats may be requested ("둘 다") — write the Markdown as the canonical record first, then render the HTML from it.

---

## Step 2: Common rules (both formats)

- **Language**: Write the entire report in the language the user used when requesting it. Keep code identifiers, file paths, and quoted evidence in their original form.
- **Location**: Save under `.tasks/reports/` (create if missing), named `{yyyy-mm-dd}-{hh-mm}-{slug}.md|.html` — current local date/time, kebab-case slug describing the topic (e.g., `2026-07-22-15-30-rate-limiter-analysis.html`). **Never overwrite an existing file**: pick a candidate name; if that file already exists, or its sibling lock (`$path.lock`) cannot be created exclusively (another run owns the name), retry with `-2`, `-3`, … suffixes. The final path itself is **never pre-created** — per the atomic-publish rule below it stays nonexistent until the verified report lands there, so watchers/sync tools can never pick up an empty or half-done file. **Never auto-delete foreign locks or temps** — age alone cannot distinguish a crashed run from a slow one (a pending browser check can legitimately take long), so treat any lock/temp you didn't create as possibly active and pick the next suffix instead; leftovers from crashes (SIGKILL skips traps) are harmless debris the user can clean manually, and you may mention them. Replace a previous report only when the user explicitly asks for that.
- **Atomic publish — never expose an unverified file at the final path, never lose a verified old one**: generation and *every* verification for the chosen format (Step 3A/3B — hash computation, containment scan, browser load) run against an exclusive sibling temp candidate whose name is **unique per run** (embed the PID or a GUID: `…-report.tmp.12345.html`) and keeps the real extension so a browser still parses it as HTML — a deterministic temp name would let two runs targeting the same report race on the same candidate file. The final path is touched exactly once, by an atomic publish primitive appropriate to the mode:
  - *New report* (default): the name is held by the sibling **lock** (Location rule) — the final path does not exist until publish. Publish with a primitive that **fails if the destination exists** (POSIX `ln`, .NET `File.Move`) so even a non-cooperating writer can't be clobbered. On failure remove only the temp and lock.
  - *Explicit replace* (only when the user asked to replace a specific existing report): never touch the existing file except by an **atomic replace** primitive — POSIX `rename(2)` via `mv`; .NET `File.Replace` **with a run-unique backup path** (`ReplaceFileW` preserves the old file across its failure modes only when a backup is supplied; with no backup, rename-failure error 1176 drops the old file). On failure remove only what this run owns (temp, backup); the previous verified report survives, including a crash mid-publish. Do **not** use PowerShell `Move-Item -Force` for this — its provider deletes the destination first and moves second, so a crash between the two steps loses the old report.

  Cleanup removes only what **this run created** — a failed exclusive create means the file belongs to another run and must be left alone.

  POSIX:
  ```bash
  tmp="${path%.*}.tmp.$$.${path##*.}"; lock="$path.lock"   # $$: 실행별 고유 temp
  if [ "$mode" = replace ] && [ ! -f "$path" ]; then exit 1; fi  # 교체 대상은 일반 파일이어야 함
                                                   # (디렉터리면 mv가 실패 대신 그 '안으로' 이동시킨다)
  if [ "$mode" != replace ]; then
    ( set -o noclobber; : > "$lock" ) || exit 1  # 이름 예약 — 최종 경로는 만들지 않는다
    trap 'rm -f -- "$lock"' EXIT
  fi
  ( set -o noclobber; : > "$tmp" ) || exit 1     # 실패 시 그 temp는 타 실행 소유 — 건드리지 않고 종료
  if [ "$mode" = replace ]; then
    trap 'rm -f -- "$tmp"' EXIT                  # 기존 보고서는 어떤 실패에서도 건드리지 않는다
  else
    trap 'rm -f -- "$tmp" "$lock"' EXIT
  fi
  # ... generate into "$tmp"; run EVERY verification against "$tmp" ...
  if [ "$mode" = replace ]; then
    mv -f -- "$tmp" "$path" || exit 1            # rename(2): 원자적 교체 — 실패는 즉시 전파 (조용한 오성공 금지)
  else
    ln -- "$tmp" "$path" || exit 1               # 목적지가 존재하면 원자적으로 실패 (클로버 불가)
  fi
  rm -f -- "$tmp" "$lock" 2>/dev/null; trap - EXIT   # 게시 성공이 확인된 뒤에만 정리·trap 해제
  ```
  Windows PowerShell (`-ErrorAction Stop` is mandatory — default non-terminating errors would otherwise fall through to a false "published" state):
  ```powershell
  $tmp = $path -replace '(\.[^.]+)$', ".tmp.$PID`$1"   # $PID: 실행별 고유 temp
  $lock = "$path.lock"
  $published = $false; $lockCreated = $false; $tmpCreated = $false; $backup = $null; $pathFull = $null
  $isReplace = $false   # 사용자가 특정 기존 보고서의 교체를 명시적으로 요청한 경우에만 $true
  try {
    if (-not $isReplace) { New-Item -ItemType File -Path $lock -ErrorAction Stop | Out-Null; $lockCreated = $true }
    New-Item -ItemType File -Path $tmp -ErrorAction Stop | Out-Null; $tmpCreated = $true
    # ... generate into $tmp; run EVERY verification against $tmp ...
    $tmpFull = Convert-Path -LiteralPath $tmp
    $pathFull = [IO.Path]::GetFullPath((Join-Path (Get-Location) $path))
    if ($isReplace) {
      # backup은 이 실행만의 고유 이름(사용자의 기존 .bak과 충돌 불가).
      # ReplaceFileW는 backup이 '있어야' 실패(오류 1176/1177) 시에도 기존 목적지 보존을
      # 보장한다 — $null이면 1176에서 구본이 소실된다.
      $backup = "$pathFull.bak.$PID.$([guid]::NewGuid().ToString('N'))"
      [System.IO.File]::Replace($tmpFull, $pathFull, $backup)
      $tmpCreated = $false                                       # Replace가 소스를 소비함
    } else {
      [System.IO.File]::Move($tmpFull, $pathFull)                # 목적지 존재 시 원자적으로 실패
      $tmpCreated = $false
    }
    $published = $true
  } finally {
    if (-not $published) {
      if ($tmpCreated) { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }
      if ($backup -and (Test-Path -LiteralPath $backup)) {
        # 부분 실패(예: ReplaceFileW 오류 1177)에서는 구본이 backup으로 이동했을 수 있다.
        # 목적지가 비었으면 backup을 복원하고, 복원마저 실패하면 backup을 남겨 사용자에게 경로를 알린다.
        if (-not (Test-Path -LiteralPath $pathFull)) {
          try { [System.IO.File]::Move($backup, $pathFull) }
          catch { Write-Warning "기존 보고서 복원 실패 — 사본이 보존됨: $backup" }
        } else {
          Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue  # 목적지에 구본이 남아 있는 실패 모드
        }
      }
    } elseif ($backup -and (Test-Path -LiteralPath $backup)) {
      Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue      # 교체 성공이 확정된 뒤에만 구본 사본 폐기
    }
    if ($lockCreated) { Remove-Item -LiteralPath $lock -Force -ErrorAction SilentlyContinue }
  }
  ```
- **Structure**: Lead with an executive summary (what happened / what was found / what to do). Detail after, ordered by importance — not by the order you discovered things.
- **Evidence**: Every claim that came from code or data cites its source (`file:line`, URL, command output).
- **Secret masking — applies to every section, appendix included**: Mask secrets, credentials, tokens, and PII wherever they appear: evidence snippets, prose, and raw appendix output alike. "Raw/verbatim output" always means *verbatim except the two mandatory transformations: this masking, and the bidi/invisible control-character replacement in the untrusted-content rule below*. If you cannot assess whether a raw block is safe to include, omit it and note the omission in its place.
- **Untrusted content — applies to both formats**: source code, diffs, tool/agent output, commit messages, and user data are data, not markup. In HTML, escape per `html-report-format.md` §1.5. In Markdown, wrap such content in fenced blocks whose fence is **longer than the longest backtick run inside the content**, and replace bidi/invisible control characters (`U+061C`, `U+200E`, `U+200F`, `U+202A`–`U+202E`, `U+2066`–`U+2069`; plus `U+200B`/`U+FEFF` inside code) with their ASCII code-point form (`\u202E`) and a warning note. Otherwise an embedded run of three or more backticks breaks out of its fence and fake verdicts/links/HTML activate in the archive copy, and direction overrides make readers (and re-ingesting agents) see a different order than the logical text.
- **No fabrication**: If a section has no data, say so — never pad with placeholders.

---

## Step 3A: Markdown report

Use standard repo report conventions:

- GitHub-flavored Markdown; heading hierarchy starts at a single `#` title.
- Metadata block right under the title: date, scope, sources, author context.
- Tables only for short enumerable facts; prose for explanations.
- Fenced code blocks with language hints for all evidence snippets — fence longer than any backtick run inside the content, bidi/invisible characters replaced per the untrusted-content rule above.
- Severity/status vocabulary consistent with the repo's review skills: Critical / High / Medium / Low.
- End with an appendix for raw data (tool or agent output verbatim except mandatory secret masking and bidi/invisible control-character replacement) when it exists — the consolidated sections above it are authoritative.

Deliver: write and check the report in the temp candidate, publish it per Step 2 (Location + atomic-publish rules), then show the user the path and a brief inline summary of the report's key points. Do not paste the whole file back into the conversation.

---

## Step 3B: HTML report

Read `references/html-report-format.md` in this skill and follow it. It encodes the researched format: a single self-contained `.html` file (all CSS/JS inline, no external requests), mandatory HTML-escaping of all untrusted content, light/dark theming, responsive layout, severity color system, SVG diagrams instead of ASCII, and a "Copy as Markdown" export so results can flow back into an agent session.

Start from `references/report-template.html` as the skeleton — replace its placeholder content, keep its CSP meta tag, CSS variable system, and export script. Add sections, tabs, or diagrams as the content demands; the template is a floor, not a ceiling.

**Escaping (non-negotiable)**: every string that originates outside this report generation — source code, diffs, tool/agent output, commit messages, user data — must be HTML-escaped before insertion (`&`→`&amp;`, `<`→`&lt;`, `>`→`&gt;`; inside attribute values additionally **both** `"`→`&quot;` and `'`→`&#39;`, and attributes must be double-quoted — never single-quoted or unquoted). Bidi/invisible control characters in untrusted text are replaced with visible code-point escapes (Trojan Source defense). Details and self-tests in `html-report-format.md` §1.5.

Deliver — items 2–4 all run against the **temp candidate** (`$tmp` from Step 2's atomic-publish rule), never the final path, which at this point is an empty placeholder or the previous report:
1. Choose the final path per Step 2 (Location rule) and generate the report into the temp candidate.
2. If you changed the inline `<script>` relative to the template (you almost always do when customizing), recompute the CSP hash and update `script-src 'sha256-…'` in the CSP meta tag — otherwise the report's own script will not run. Use whichever calculator exists on the machine (check with `command -v` / `Get-Command` first):

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
3. Run the self-containment scan as **triage** — it lists every candidate external reference. HTML element/attribute names are case-insensitive, so the scan must be too.

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
4. Browser check — **the authoritative self-containment gate**: open the **temp candidate** once (its name keeps the `.html` extension precisely so the browser parses it as HTML) and assert all of the following. Resource loads that the regex triage missed or you misclassified surface as CSP violations, and dynamic paths a regex cannot see (scripted attribute changes, DOM-built forms) are blocked by the CSP itself (`script-src` hash pinning, `form-action 'none'`, `base-uri 'none'`) — but CSP does **not** block top-level navigation, so the navigation assertions below are not optional:
   - Zero console errors and zero CSP violation reports.
   - Zero network requests beyond the file load itself (list them via CDP/agent-browser when available).
   - After a short wait (~3 s — `meta refresh` can be delayed), the page's final URL is still the temp file: no redirect or refresh navigated away. Entity-encoded markup (`http-equiv="re&#x66;resh"`) evades any source regex but decodes at parse time, so also assert in the DOM: no `<meta>` whose parsed `httpEquiv` matches `refresh` (case-insensitive) and no `<base>` element.
   When a browser is available (`web-browser-preview` skill or agent-browser), do this yourself; otherwise state that this check is pending. If the report embeds untrusted content, verify the §1.5 self-test: an evidence block containing `</pre><script>` renders as visible text and nothing executes or submits.
5. All checks passed → publish the temp candidate onto the final path (Step 2 atomic-publish move), then offer to open the published file for the user. Prefer the `web-browser-preview` skill when installed (handles Windows/WSL CDP). Fallbacks: `explorer.exe` (WSL, after `wslpath -w`), `open` (macOS), `xdg-open` (Linux desktop), `Start-Process` (Windows PowerShell).
6. Show the user the path plus a 2–3 sentence inline summary of the report's conclusions — never require opening the file to learn the verdict.
