# Atomic Publish — Reference Implementations

Concrete code for the Location + atomic-publish guarantees stated in SKILL.md Step 2. The guarantees are normative; these snippets are one correct way to satisfy them.

Recap of what must hold:

- The report is generated into a **sibling temp candidate whose name is unique per run** (embed the PID or a GUID: `…-report.tmp.12345.html`) and which keeps the real extension, so a browser still parses it as HTML. A deterministic temp name would let two runs targeting the same report race on the same candidate file.
- **Every** verification for the chosen format (Step 3A/3B — hash computation, containment scan, browser load) runs against the temp candidate, never against the final path.
- The final path is touched **exactly once**, by an atomic publish primitive.
- Cleanup removes only what **this run created** — a failed exclusive create means the file belongs to another run and must be left alone.

## Mode: new report (default)

The name is held by the sibling **lock** (`$path.lock`); the final path does not exist until publish. Publish with a primitive that **fails if the destination exists** (POSIX `ln`, .NET `File.Move`) so even a non-cooperating writer cannot be clobbered. On failure remove only the temp and lock.

## Mode: explicit replace (rare)

Only when the user asked to replace a specific existing report. Never touch the existing file except by an **atomic replace** primitive — POSIX `rename(2)` via `mv`; .NET `File.Replace` **with a run-unique backup path** (`ReplaceFileW` preserves the old file across its failure modes only when a backup is supplied; with no backup, rename-failure error 1176 drops the old file). On failure remove only what this run owns (temp, backup); the previous verified report survives, including a crash mid-publish.

Do **not** use PowerShell `Move-Item -Force` for this — its provider deletes the destination first and moves second, so a crash between the two steps loses the old report.

## POSIX

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
rm -f -- "$tmp" 2>/dev/null                        # 게시 성공이 확인된 뒤에만 정리
[ "$mode" = replace ] || rm -f -- "$lock" 2>/dev/null   # lock은 이 실행이 만든 모드에서만 제거
trap - EXIT
```

## Windows PowerShell

`-ErrorAction Stop` is mandatory — default non-terminating errors would otherwise fall through to a false "published" state.

**Both `.NET` paths must be absolute.** `[System.IO.File]::Move`/`Replace` resolve relative paths against the *process* working directory (`[Environment]::CurrentDirectory`), which PowerShell does **not** keep in sync with its own location — so a relative path would publish to whatever directory the process was launched from. Normalize with the provider's unresolved conversion:

- `$ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($path)` — converts a PowerShell path to a provider path **without requiring it to exist**, which is exactly what the final path needs (it stays nonexistent until publish). It applies the provider's own rules, so a relative path anchors to the current PowerShell location, an already-rooted path is returned as-is, and a UNC path stays UNC. Wildcard metacharacters (`[`, `]`, `*`, `?`) are treated literally — this is the same conversion PowerShell's own `-LiteralPath` parameters use.
- `Convert-Path` / `Resolve-Path` are **not** usable for the final path: both fail on a path that does not exist yet. `Convert-Path -LiteralPath $tmp` is fine for the temp candidate, which was just created.
- Do **not** build the absolute path as `[IO.Path]::GetFullPath((Join-Path (Get-Location) $path))`. `Join-Path` blindly concatenates, so an already-rooted `$path` breaks: `C:\Temp\x.md` yields `C:\cwd\C:\Temp\x.md` and `GetFullPath` **throws** on the embedded colon, while `\\server\share\x.md` yields `C:\cwd\\server\share\x.md`, whose duplicate separators collapse to `C:\cwd\server\share\x.md` — a **silently wrong destination inside the current directory**. A `[IO.Path]::IsPathRooted($path)` branch fixes the crash but still resolves relative paths against the process directory rather than the PowerShell location, and treats a drive-relative `\reports\x.md` as rooted, anchoring it to the process drive.

Run the conversion while the current location is on a filesystem drive — a relative path evaluated from a non-filesystem provider location (e.g. `HKLM:\`) would resolve under that provider and then fail in the `.NET` call.

```powershell
$tmp = $path -replace '(\.[^.]+)$', ".tmp.$PID`$1"   # $PID: 실행별 고유 temp
$lock = "$path.lock"
$published = $false; $lockCreated = $false; $tmpCreated = $false; $backup = $null; $pathFull = $null
$isReplace = $false   # 사용자가 특정 기존 보고서의 교체를 명시적으로 요청한 경우에만 $true
try {
  if (-not $isReplace) { New-Item -ItemType File -Path $lock -ErrorAction Stop | Out-Null; $lockCreated = $true }
  New-Item -ItemType File -Path $tmp -ErrorAction Stop | Out-Null; $tmpCreated = $true
  # ... generate into $tmp; run EVERY verification against $tmp ...
  $tmpFull = Convert-Path -LiteralPath $tmp   # temp는 이미 존재하므로 Convert-Path로 충분
  # 최종 경로는 아직 존재하지 않는다 — Convert-Path/Resolve-Path는 여기서 실패한다.
  # provider의 unresolved 변환은 상대·절대·UNC를 모두 올바른 절대 경로로 만든다.
  $pathFull = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($path)
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
