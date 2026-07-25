$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8

$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Import-Module (Join-Path $root 'scripts\Installer.Common.psm1') -Force

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw "Assertion failed: $Message" }
}

# Resolves the same interpreter the installer registers for Windows hooks.
function Get-WorkflowHookHostPath {
    foreach ($candidate in @('powershell.exe', 'pwsh.exe', 'pwsh')) {
        $resolved = @(Get-Command -Name $candidate -CommandType Application -ErrorAction SilentlyContinue)
        if ($resolved.Count -gt 0) { return [string]$resolved[0].Source }
    }
    return $null
}

# Collects text from an already-started async pipe read without ever waiting indefinitely.
function Receive-ProcessStreamText {
    param($Task, [int]$TimeoutMilliseconds)
    if ($null -eq $Task) { return '' }
    if ($TimeoutMilliseconds -lt 0) { $TimeoutMilliseconds = 0 }
    try {
        # Task.Wait(int) returns $false on timeout; a faulted or cancelled task throws instead.
        if (-not $Task.Wait($TimeoutMilliseconds)) { return '' }
        return [string]$Task.Result
    } catch {
        return ''
    }
}

# Milliseconds left before an absolute deadline measured on the same running stopwatch. Both pipe
# reads draw from one deadline, so the drain window is a single budget instead of one per stream.
function Get-RemainingMilliseconds {
    param($Watch, [double]$DeadlineMilliseconds)
    $remaining = $DeadlineMilliseconds - $Watch.Elapsed.TotalMilliseconds
    if ($remaining -le 0) { return 0 }
    return [int][math]::Ceiling($remaining)
}

# Runs the hook exactly as the installed command does: a fresh process reading JSON from stdin.
# Every wait is bounded, so a hook that stops responding fails this test instead of hanging CI --
# that silent-no-output regression is the main thing this section exists to catch.
function Invoke-WorkflowHookProcess {
    param([string]$HostPath, [string]$HookPath, [byte[]]$PayloadBytes, $Encoding, [double]$TimeoutSeconds)
    $timeoutMilliseconds = [int][math]::Ceiling($TimeoutSeconds * 1000)
    # One grace window shared by process teardown and both pipe drains, and part of the measured
    # duration: a caller of the installed hook waits for the pipes too, so time spent here is time
    # the user spends staring at nothing. Splitting it per stream would let a grandchild holding a
    # single pipe open add this much again outside the reported number.
    $drainMilliseconds = 2000
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $HostPath
    $startInfo.Arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $HookPath + '"'
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardInput = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.StandardOutputEncoding = $Encoding
    $startInfo.StandardErrorEncoding = $Encoding
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    $standardOutput = ''
    $standardError = ''
    $exitCode = -1
    $timedOut = $false
    $outputTask = $null
    $errorTask = $null
    $watch = [Diagnostics.Stopwatch]::StartNew()
    try {
        $process.Start() | Out-Null
        # Both pipes drain asynchronously. A synchronous stdout ReadToEnd would block forever when
        # the hook hangs, which is precisely the case the timeout below has to report as a failure.
        $outputTask = $process.StandardOutput.ReadToEndAsync()
        $errorTask = $process.StandardError.ReadToEndAsync()
        # Raw byte writes avoid PowerShell 5.1's lack of ProcessStartInfo.StandardInputEncoding.
        $inputStream = $process.StandardInput.BaseStream
        $inputStream.Write($PayloadBytes, 0, $PayloadBytes.Length)
        $inputStream.Flush()
        $process.StandardInput.Close()
        # WaitForExit(int) returns $false on timeout instead of throwing, so the result is checked.
        if ($process.WaitForExit($timeoutMilliseconds)) {
            $exitCode = $process.ExitCode
        } else {
            $timedOut = $true
            # Kill() throws if the process raced to exit just now; the run still counts as a timeout.
            try { $process.Kill() } catch { }
            $process.WaitForExit($drainMilliseconds) | Out-Null
        }
        # Read the drained text only after the process is gone, and with a bounded wait: a grandchild
        # that inherited the handles can hold the pipes open past the kill. The deadline is absolute
        # and anchored here, so stdout and stderr split one window instead of taking one each.
        $drainDeadlineMilliseconds = $watch.Elapsed.TotalMilliseconds + $drainMilliseconds
        $standardOutput = Receive-ProcessStreamText -Task $outputTask -TimeoutMilliseconds (Get-RemainingMilliseconds -Watch $watch -DeadlineMilliseconds $drainDeadlineMilliseconds)
        $standardError = Receive-ProcessStreamText -Task $errorTask -TimeoutMilliseconds (Get-RemainingMilliseconds -Watch $watch -DeadlineMilliseconds $drainDeadlineMilliseconds)
    } finally {
        # Stopped only once every wait is over, so Seconds is the whole time a caller would have
        # blocked -- process run plus pipe drain -- and the hard limit below can actually bind it.
        $watch.Stop()
        $process.Dispose()
    }
    return [pscustomobject][ordered]@{
        ExitCode = $exitCode
        StandardOutput = $standardOutput
        StandardError = $standardError
        Seconds = $watch.Elapsed.TotalSeconds
        TimedOut = $timedOut
    }
}

# Verifies one hook run produced the reminder contract the clients consume, inside the hard limit
# that the registered hook timeout imposes. Every run is held to it, cold start included.
function Assert-WorkflowHookRun {
    param($Result, [string]$Label, [double]$HardLimitSeconds)
    Assert-True (-not $Result.TimedOut) ("{0} answers before the registered {1:N1}s hook timeout (process never exited and was killed after {2:N3}s)" -f $Label, $HardLimitSeconds, $Result.Seconds)
    Assert-True ($Result.Seconds -lt $HardLimitSeconds) ("{0} finishes inside the registered {1:N1}s hook timeout (took {2:N3}s)" -f $Label, $HardLimitSeconds, $Result.Seconds)
    Assert-True ($Result.ExitCode -eq 0) "$Label exits with code 0 (stderr: $($Result.StandardError))"
    $parsed = $null
    $parsedOk = $false
    try {
        $parsed = $Result.StandardOutput | ConvertFrom-Json
        $parsedOk = $true
    } catch {
        $parsedOk = $false
    }
    Assert-True $parsedOk "$Label writes valid JSON to stdout"
    Assert-True ($null -ne $parsed -and @($parsed.PSObject.Properties.Name) -contains 'hookSpecificOutput') "$Label emits hookSpecificOutput"
    $hookOutput = $parsed.hookSpecificOutput
    Assert-True (@($hookOutput.PSObject.Properties.Name) -contains 'additionalContext') "$Label emits additionalContext"
    Assert-True (-not [string]::IsNullOrWhiteSpace([string]$hookOutput.additionalContext)) "$Label additionalContext is non-empty"
}

$temporaryRoot = Join-Path ([IO.Path]::GetTempPath()) ('skills 설치 행렬 ' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temporaryRoot | Out-Null
try {
    $components = @(Get-SupportedComponents -Client claude -Platform windows -Kind skill)
    $plan = @($components | Where-Object { $_.name -eq 'plan-and-build' })[0]

    # Project copy install, reinstall ownership, modified-copy preservation, and removal.
    $project = Join-Path $temporaryRoot 'Project With Space 한글'
    New-Item -ItemType Directory -Path $project | Out-Null
    $layout = Get-InstallLayout -Scope project -Root $project
    Assert-True (Install-ManagedComponent -Layout $layout -Component $plan -Client claude -TargetDirectory $layout.ClaudeSkills -Method copy) 'project copy install'
    $target = Join-Path $layout.ClaudeSkills 'plan-and-build'
    Assert-True (Test-Path (Join-Path $target 'SKILL.md')) 'copied skill exists'
    Assert-True (Install-ManagedComponent -Layout $layout -Component $plan -Client claude -TargetDirectory $layout.ClaudeSkills -Method copy) 'owned reinstall'
    Add-Content -LiteralPath (Join-Path $target 'SKILL.md') -Value '# user edit' -Encoding UTF8
    Assert-True (-not (Remove-ManagedComponent -Layout $layout -Component $plan -Client claude -TargetDirectory $layout.ClaudeSkills)) 'modified copy is preserved'
    Assert-True (Test-Path -LiteralPath $target) 'modified target remains'

    # Claude/Codex x global/project: skills and agents copy, reinstall, and remove.
    foreach ($scope in @('global', 'project')) {
        foreach ($client in @('claude', 'codex')) {
            $matrixRoot = Join-Path $temporaryRoot ("Matrix $scope $client 한글")
            New-Item -ItemType Directory -Path $matrixRoot | Out-Null
            $matrixLayout = Get-InstallLayout -Scope $scope -Root $matrixRoot
            $skillDirectory = if ($client -eq 'claude') { $matrixLayout.ClaudeSkills } else { $matrixLayout.CodexSkills }
            $agentDirectory = if ($client -eq 'claude') { $matrixLayout.ClaudeAgents } else { $matrixLayout.CodexAgents }
            foreach ($matrixSkill in @(Get-SupportedComponents -Client $client -Platform windows -Kind skill)) {
                Assert-True (Install-ManagedComponent -Layout $matrixLayout -Component $matrixSkill -Client $client -TargetDirectory $skillDirectory -Method copy) "$scope $client $($matrixSkill.name) skill copy"
                Assert-True (Install-ManagedComponent -Layout $matrixLayout -Component $matrixSkill -Client $client -TargetDirectory $skillDirectory -Method copy) "$scope $client $($matrixSkill.name) skill reinstall"
            }
            foreach ($matrixAgent in @(Get-SupportedComponents -Client $client -Platform windows -Kind agent)) {
                Assert-True (Install-ManagedComponent -Layout $matrixLayout -Component $matrixAgent -Client $client -TargetDirectory $agentDirectory -Method symlink) "$scope $client $($matrixAgent.name) agent forced copy"
            }
            foreach ($matrixAgent in @(Get-SupportedComponents -Client $client -Platform windows -Kind agent)) {
                Assert-True (Remove-ManagedComponent -Layout $matrixLayout -Component $matrixAgent -Client $client -TargetDirectory $agentDirectory) "$scope $client $($matrixAgent.name) agent remove"
            }
            foreach ($matrixSkill in @(Get-SupportedComponents -Client $client -Platform windows -Kind skill)) {
                Assert-True (Remove-ManagedComponent -Layout $matrixLayout -Component $matrixSkill -Client $client -TargetDirectory $skillDirectory) "$scope $client $($matrixSkill.name) skill remove"
            }
        }
    }

    # Skill link request either creates a local link or safely falls back to copy.
    $linkRoot = Join-Path $temporaryRoot 'Link permission fallback'
    New-Item -ItemType Directory -Path $linkRoot | Out-Null
    $linkLayout = Get-InstallLayout -Scope project -Root $linkRoot
    Assert-True (Install-ManagedComponent -Layout $linkLayout -Component $plan -Client claude -TargetDirectory $linkLayout.ClaudeSkills -Method symlink) 'skill link or copy fallback'
    $linkManifest = Get-Content -LiteralPath $linkLayout.Manifest -Raw | ConvertFrom-Json
    Assert-True (@('symlink', 'copy') -contains [string]$linkManifest.entries[0].method) 'link method recorded'
    Assert-True (Remove-ManagedComponent -Layout $linkLayout -Component $plan -Client claude -TargetDirectory $linkLayout.ClaudeSkills) 'linked/fallback skill remove'

    # When this Windows account can create links, exercise an actual local symlink lifecycle.
    $module = Get-Module Installer.Common
    $originalRepositoryRoot = & $module { $script:RepositoryRoot }
    $localRepository = Join-Path $temporaryRoot 'Local Repository'
    New-Item -ItemType Directory -Path (Join-Path $localRepository 'skills') -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $root 'skills\plan-and-build') -Destination (Join-Path $localRepository 'skills\plan-and-build') -Recurse
    $probeTarget = Join-Path $temporaryRoot 'link-probe'
    $canCreateLink = $false
    try {
        New-Item -ItemType SymbolicLink -Path $probeTarget -Target (Join-Path $localRepository 'skills\plan-and-build') | Out-Null
        $canCreateLink = $true
    } catch {
        Write-Host 'Actual symlink lifecycle skipped: Windows link privilege is unavailable.' -ForegroundColor Yellow
    } finally {
        if (Test-Path -LiteralPath $probeTarget) { Remove-Item -LiteralPath $probeTarget -Force }
    }
    if ($canCreateLink) {
        & $module { $script:RepositoryRoot = $args[0] } $localRepository
        try {
            $actualLinkRoot = Join-Path $temporaryRoot 'Actual Link'
            New-Item -ItemType Directory -Path $actualLinkRoot | Out-Null
            $actualLinkLayout = Get-InstallLayout -Scope project -Root $actualLinkRoot
            $actualLinkTarget = Join-Path $actualLinkLayout.ClaudeSkills 'plan-and-build'
            $actualLinkSource = Join-Path $localRepository 'skills\plan-and-build'
            Assert-True (Test-SymbolicLinkEligible -Layout $actualLinkLayout) 'local Windows link is eligible'
            Assert-True (Install-ManagedComponent -Layout $actualLinkLayout -Component $plan -Client claude -TargetDirectory $actualLinkLayout.ClaudeSkills -Method symlink) 'actual symlink install'
            Assert-True ((Get-Item -LiteralPath $actualLinkTarget -Force).LinkType -eq 'SymbolicLink') 'actual target is a symbolic link'
            $actualLinkManifest = Get-Content -LiteralPath $actualLinkLayout.Manifest -Raw | ConvertFrom-Json
            Assert-True ([string]$actualLinkManifest.entries[0].method -eq 'symlink') 'actual symlink method recorded'
            Assert-True (Install-ManagedComponent -Layout $actualLinkLayout -Component $plan -Client claude -TargetDirectory $actualLinkLayout.ClaudeSkills -Method symlink) 'actual symlink reinstall'
            Assert-True (Remove-ManagedComponent -Layout $actualLinkLayout -Component $plan -Client claude -TargetDirectory $actualLinkLayout.ClaudeSkills) 'actual symlink remove'
            Assert-True (-not (Test-Path -LiteralPath $actualLinkTarget)) 'actual symlink target is removed'
            Assert-True (Test-Path -LiteralPath (Join-Path $actualLinkSource 'SKILL.md') -PathType Leaf) 'actual symlink source survives removal'
        } finally {
            & $module { $script:RepositoryRoot = $args[0] } $originalRepositoryRoot
        }
    }

    # A lost manifest never authorizes deletion of an otherwise matching copy.
    $lostRoot = Join-Path $temporaryRoot 'Manifest Lost'
    New-Item -ItemType Directory -Path $lostRoot | Out-Null
    $lostLayout = Get-InstallLayout -Scope project -Root $lostRoot
    Assert-True (Install-ManagedComponent -Layout $lostLayout -Component $plan -Client claude -TargetDirectory $lostLayout.ClaudeSkills -Method copy) 'manifest-loss setup'
    Remove-Item -LiteralPath $lostLayout.Manifest -Force
    Assert-True (-not (Remove-ManagedComponent -Layout $lostLayout -Component $plan -Client claude -TargetDirectory $lostLayout.ClaudeSkills)) 'manifest-loss preserve'
    Assert-True (Test-Path -LiteralPath (Join-Path $lostLayout.ClaudeSkills 'plan-and-build')) 'unverified copy remains'

    # Foreign same-name item is never replaced.
    $foreignProject = Join-Path $temporaryRoot 'foreign'
    New-Item -ItemType Directory -Path (Join-Path $foreignProject '.claude\skills\plan-and-build') -Force | Out-Null
    $foreignFile = Join-Path $foreignProject '.claude\skills\plan-and-build\SKILL.md'
    [IO.File]::WriteAllText($foreignFile, 'foreign')
    $foreignLayout = Get-InstallLayout -Scope project -Root $foreignProject
    Assert-True (-not (Install-ManagedComponent -Layout $foreignLayout -Component $plan -Client claude -TargetDirectory $foreignLayout.ClaudeSkills -Method copy)) 'foreign item is skipped'
    Assert-True ((Get-Content -LiteralPath $foreignFile -Raw) -eq 'foreign') 'foreign content unchanged'

    # Codex JSON merge, TOML state record/restore, exact foreign-hook preservation.
    $globalRoot = Join-Path $temporaryRoot 'profile'
    New-Item -ItemType Directory -Path (Join-Path $globalRoot '.codex') -Force | Out-Null
    $global = Get-InstallLayout -Scope global -Root $globalRoot
    [IO.File]::WriteAllText($global.CodexConfig, "[features]`r`nhooks = false`r`nother = true`r`n")
    $foreignHook = [ordered]@{ hooks = [ordered]@{ UserPromptSubmit = @([ordered]@{ hooks = @([ordered]@{ type = 'command'; command = 'foreign.exe'; timeout = 7 }) }) } }
    [IO.File]::WriteAllText($global.CodexHooksFile, ($foreignHook | ConvertTo-Json -Depth 10))
    Assert-True (Install-WorkflowHook -Layout $global -Client codex -EnableCodexHooks) 'Codex hook install'
    $hookJson = Get-Content -LiteralPath $global.CodexHooksFile -Raw | ConvertFrom-Json
    Assert-True (@($hookJson.hooks.UserPromptSubmit).Count -eq 2) 'foreign and managed hooks coexist'
    $managed = @($hookJson.hooks.UserPromptSubmit)[1].hooks[0]
    Assert-True ($managed.PSObject.Properties.Name -contains 'commandWindows') 'Codex commandWindows exists'
    Assert-True ((Get-Content -LiteralPath $global.CodexConfig -Raw) -match 'hooks\s*=\s*true') 'Codex hooks enabled'
    Assert-True (Remove-WorkflowHook -Layout $global -Client codex) 'Codex hook removal'
    $afterJson = Get-Content -LiteralPath $global.CodexHooksFile -Raw | ConvertFrom-Json
    Assert-True (@($afterJson.hooks.UserPromptSubmit).Count -eq 1) 'only managed hook removed'
    $afterConfig = Get-Content -LiteralPath $global.CodexConfig -Raw
    Assert-True ($afterConfig -match 'hooks\s*=\s*false') 'Codex hook state restored'
    Assert-True ($afterConfig -match 'other\s*=\s*true') 'unrelated TOML preserved'

    # Invalid Claude JSON rolls back the new hook file and manifest entry.
    $rollbackRoot = Join-Path $temporaryRoot 'rollback'
    New-Item -ItemType Directory -Path (Join-Path $rollbackRoot '.claude') -Force | Out-Null
    $rollback = Get-InstallLayout -Scope global -Root $rollbackRoot
    [IO.File]::WriteAllText($rollback.ClaudeSettings, '{ invalid json')
    $failed = $false
    try { Install-WorkflowHook -Layout $rollback -Client claude | Out-Null } catch { $failed = $true }
    Assert-True $failed 'invalid JSON fails installation'
    Assert-True (-not (Test-Path (Join-Path $rollback.ClaudeHooks 'claude-code-skills-workflow.ps1'))) 'hook file rolled back'
    Assert-True ((Get-Content -LiteralPath $rollback.ClaudeSettings -Raw) -eq '{ invalid json') 'invalid JSON untouched'

    # Existing unowned hook file is preserved.
    $ownedRoot = Join-Path $temporaryRoot 'unowned-hook'
    $owned = Get-InstallLayout -Scope global -Root $ownedRoot
    New-Item -ItemType Directory -Path $owned.ClaudeHooks -Force | Out-Null
    $unownedHook = Join-Path $owned.ClaudeHooks 'claude-code-skills-workflow.ps1'
    [IO.File]::WriteAllText($unownedHook, 'foreign hook')
    Assert-True (-not (Install-WorkflowHook -Layout $owned -Client claude)) 'unowned hook skipped'
    Assert-True ((Get-Content -LiteralPath $unownedHook -Raw) -eq 'foreign hook') 'unowned hook content preserved'

    # Inline TOML feature state is enabled and restored without losing peers.
    $inlineRoot = Join-Path $temporaryRoot 'inline TOML'
    New-Item -ItemType Directory -Path (Join-Path $inlineRoot '.codex') -Force | Out-Null
    $inline = Get-InstallLayout -Scope global -Root $inlineRoot
    [IO.File]::WriteAllText($inline.CodexConfig, "features = { hooks = false, other = true }`r`n")
    $inlineState = Get-CodexHookFeatureState -Path $inline.CodexConfig
    Assert-True ($inlineState.Value -eq $false -and $inlineState.Inline) 'inline feature state detected'
    Assert-True (Install-WorkflowHook -Layout $inline -Client codex -EnableCodexHooks) 'inline feature hook install'
    Assert-True ((Get-Content -LiteralPath $inline.CodexConfig -Raw) -match 'hooks\s*=\s*true') 'inline hooks enabled'
    Assert-True (Remove-WorkflowHook -Layout $inline -Client codex) 'inline feature hook remove'
    $inlineAfter = Get-Content -LiteralPath $inline.CodexConfig -Raw
    Assert-True ($inlineAfter -match 'hooks\s*=\s*false') 'inline hooks restored'
    Assert-True ($inlineAfter -match 'other\s*=\s*true') 'inline peer preserved'
    [IO.File]::WriteAllText($inline.CodexConfig, "hooks = { command = 'foreign.exe' }`r`n")
    Assert-True (Test-CodexInlineHooks -Path $inline.CodexConfig) 'root inline hooks conflict detected'
    $quotedInline = "features = { hooks = false, note = `"foo#bar`" }`r`n"
    [IO.File]::WriteAllText($inline.CodexConfig, $quotedInline)
    $quotedRejected = $false
    try { Get-CodexHookFeatureState -Path $inline.CodexConfig | Out-Null } catch { $quotedRejected = $true }
    Assert-True $quotedRejected 'quoted inline feature table requires manual review'
    Assert-True ((Get-Content -LiteralPath $inline.CodexConfig -Raw) -eq $quotedInline) 'quoted inline TOML remains unchanged'

    # Feature-looking text inside TOML multiline strings is never treated as configuration.
    $multilineRoot = Join-Path $temporaryRoot 'multiline TOML'
    New-Item -ItemType Directory -Path (Join-Path $multilineRoot '.codex') -Force | Out-Null
    $multiline = Get-InstallLayout -Scope global -Root $multilineRoot
    $multilineText = "developer_instructions = `"`"`"`r`nfeatures.hooks = false`r`n`"`"`"`r`n"
    [IO.File]::WriteAllText($multiline.CodexConfig, $multilineText)
    $multilineState = Get-CodexHookFeatureState -Path $multiline.CodexConfig
    Assert-True ($null -eq $multilineState.Value) 'multiline string does not define hook feature state'
    Assert-True (Install-WorkflowHook -Layout $multiline -Client codex -EnableCodexHooks) 'hook install with multiline string'
    Assert-True ((Get-Content -LiteralPath $multiline.CodexConfig -Raw) -eq $multilineText) 'multiline string remains byte-for-byte unchanged'
    Assert-True (Remove-WorkflowHook -Layout $multiline -Client codex) 'hook remove with multiline string'

    $escapedMultilineText = "developer_instructions = `"`"`"`r`nescaped delimiter = \`"`"`"`r`nfeatures.hooks = false`r`n`"`"`"`r`n"
    [IO.File]::WriteAllText($multiline.CodexConfig, $escapedMultilineText)
    $escapedMultilineState = Get-CodexHookFeatureState -Path $multiline.CodexConfig
    Assert-True ($null -eq $escapedMultilineState.Value) 'escaped triple quote does not end a multiline basic string'
    Assert-True (-not (Test-CodexInlineHooks -Path $multiline.CodexConfig)) 'multiline string content is not an inline hook'

    # The inline-hook detection contract is shared with the Python implementations through
    # tests/fixtures/codex_inline_hooks.json. Every case in that file is replayed here, discovered by
    # enumeration rather than by name or count, so a case added for one implementation can never
    # quietly skip this one. The expectation used is `lineBased`: this detector has no TOML parser,
    # and the fixture records where it deliberately over-detects relative to the structural answer.
    $inlineFixturePath = Join-Path $root 'tests\fixtures\codex_inline_hooks.json'
    # A missing fixture fails here rather than warning and moving on. The skips elsewhere in this
    # file cover environment facts this machine cannot change (no PowerShell host, not native
    # Windows); an absent fixture is a repository-state fact, and tolerating it would silently
    # delete this side of a three-implementation contract while the suite still reports success.
    Assert-True (Test-Path -LiteralPath $inlineFixturePath -PathType Leaf) "Codex inline-hook contract fixture exists at $inlineFixturePath"
    $inlineFixture = [IO.File]::ReadAllText($inlineFixturePath) | ConvertFrom-Json
    # PowerShell 5.1 ConvertFrom-Json has no -AsHashtable, so every optional field is probed
    # through PSObject.Properties instead of being dereferenced blindly under StrictMode 2.0.
    Assert-True (@($inlineFixture.PSObject.Properties.Name) -contains 'cases') 'inline hook fixture declares cases'
    $inlineFixtureCases = @($inlineFixture.cases)
    Assert-True ($inlineFixtureCases.Count -gt 0) 'inline hook fixture declares at least one case'
    $fixtureConfigRoot = Join-Path $temporaryRoot 'Codex inline fixture'
    New-Item -ItemType Directory -Path $fixtureConfigRoot -Force | Out-Null
    $fixtureCaseIndex = 0
    foreach ($fixtureCase in $inlineFixtureCases) {
        $fixtureCaseIndex++
        $fixtureCaseFields = @($fixtureCase.PSObject.Properties.Name)
        $fixtureCaseName = if ($fixtureCaseFields -contains 'name') { [string]$fixtureCase.name } else { "case $fixtureCaseIndex" }
        # A case carries its TOML inline; a future case may instead point at a file beside the
        # fixture, so both spellings resolve to the same replay path.
        $fixtureCaseToml = $null
        if (($fixtureCaseFields -contains 'toml') -and ($null -ne $fixtureCase.toml)) {
            $fixtureCaseToml = [string]$fixtureCase.toml
        } elseif (($fixtureCaseFields -contains 'tomlFile') -and ($null -ne $fixtureCase.tomlFile)) {
            $fixtureCaseTomlPath = Join-Path (Split-Path -Parent $inlineFixturePath) ([string]$fixtureCase.tomlFile)
            Assert-True (Test-Path -LiteralPath $fixtureCaseTomlPath -PathType Leaf) "fixture case '$fixtureCaseName' references an existing TOML file"
            $fixtureCaseToml = [IO.File]::ReadAllText($fixtureCaseTomlPath)
        }
        Assert-True ($null -ne $fixtureCaseToml) "fixture case '$fixtureCaseName' provides TOML content"
        Assert-True ($fixtureCaseFields -contains 'lineBased') "fixture case '$fixtureCaseName' declares the line-based expectation"
        # The index names the file: a case name is free text and must never reach a path.
        $fixtureConfigPath = Join-Path $fixtureConfigRoot ('case-{0:D3}.toml' -f $fixtureCaseIndex)
        [IO.File]::WriteAllText($fixtureConfigPath, $fixtureCaseToml, $utf8)
        $expectedInline = [bool]$fixtureCase.lineBased
        $actualInline = [bool](Test-CodexInlineHooks -Path $fixtureConfigPath)
        $divergenceNote = if (($fixtureCaseFields -contains 'knownDivergence') -and [bool]$fixtureCase.knownDivergence) { ' [known divergence from the structural parser]' } else { '' }
        Assert-True ($actualInline -eq $expectedInline) ("Test-CodexInlineHooks returns {0} for fixture case '{1}'{2} (returned {3})" -f $expectedInline, $fixtureCaseName, $divergenceNote, $actualInline)
    }
    Write-Host ('Codex inline-hook fixture: {0} case(s) replayed against Test-CodexInlineHooks.' -f $inlineFixtureCases.Count) -ForegroundColor Cyan

    # A valid v1-owned Windows copy migrates and is rewritten as a v2 Windows entry.
    $legacyRoot = Join-Path $temporaryRoot 'Legacy Profile'
    $legacyLayout = Get-InstallLayout -Scope global -Root $legacyRoot
    $legacyTarget = Join-Path $legacyLayout.LegacyCodexSkills 'plan-and-build'
    New-Item -ItemType Directory -Path (Split-Path -Parent $legacyTarget) -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $root 'skills\plan-and-build') -Destination $legacyTarget -Recurse
    New-Item -ItemType Directory -Path $legacyLayout.ManifestDirectory -Force | Out-Null
    $legacyHash = & (Get-Module Installer.Common) { Get-LegacyPosixContentHash -Path $args[0] } $legacyTarget
    $legacyRow = "codex-skill`t$legacyTarget`tcopy`t$(Join-Path $root 'skills\plan-and-build')`t$legacyHash`t2026-01-01T00:00:00Z`r`n"
    [IO.File]::WriteAllText($legacyLayout.LegacyManifest, "#claude-code-skills-manifest v1`r`n$legacyRow")
    Invoke-LegacyCodexSkillMigration -Layout $legacyLayout
    Assert-True (-not (Test-Path -LiteralPath $legacyTarget)) 'legacy path removed after migration'
    Assert-True (Test-Path -LiteralPath (Join-Path $legacyLayout.CodexSkills 'plan-and-build')) 'official Codex skill path populated'
    $migratedManifest = Get-Content -LiteralPath $legacyLayout.Manifest -Raw | ConvertFrom-Json
    $migratedEntry = @($migratedManifest.entries | Where-Object { $_.component -eq 'plan-and-build' })[0]
    Assert-True ($migratedManifest.version -eq 2 -and $migratedEntry.platform -eq 'windows') 'v1 migration recorded as Windows v2'

    # A POSIX v2 hash proves ownership for native Windows migration too.
    $v2Root = Join-Path $temporaryRoot 'POSIX v2 Profile'
    $v2Layout = Get-InstallLayout -Scope global -Root $v2Root
    $v2LegacyTarget = Join-Path $v2Layout.LegacyCodexSkills 'plan-and-build'
    New-Item -ItemType Directory -Path (Split-Path -Parent $v2LegacyTarget) -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $root 'skills\plan-and-build') -Destination $v2LegacyTarget -Recurse
    New-Item -ItemType Directory -Path $v2Layout.ManifestDirectory -Force | Out-Null
    $v2LegacyHash = & $module { Get-LegacyPosixContentHash -Path $args[0] } $v2LegacyTarget
    $v2Manifest = [ordered]@{ version = 2; entries = @([ordered]@{
        platform = 'posix'; scope = 'global'; client = 'codex'; kind = 'skill'; component = 'plan-and-build'
        target = $v2LegacyTarget; method = 'copy'; source = (Join-Path $root 'skills\plan-and-build')
        hash = $v2LegacyHash; installedAt = '2026-01-01T00:00:00Z'
    }) }
    [IO.File]::WriteAllText($v2Layout.Manifest, ($v2Manifest | ConvertTo-Json -Depth 10))
    Invoke-LegacyCodexSkillMigration -Layout $v2Layout
    Assert-True (-not (Test-Path -LiteralPath $v2LegacyTarget)) 'POSIX v2 legacy path removed'
    Assert-True (Test-Path -LiteralPath (Join-Path $v2Layout.CodexSkills 'plan-and-build')) 'POSIX v2 ownership migrates to official path'

    # Empty directories count as user modifications and prevent removal.
    $emptyDirectoryRoot = Join-Path $temporaryRoot 'Empty Directory Modification'
    New-Item -ItemType Directory -Path $emptyDirectoryRoot | Out-Null
    $emptyDirectoryLayout = Get-InstallLayout -Scope project -Root $emptyDirectoryRoot
    Assert-True (Install-ManagedComponent -Layout $emptyDirectoryLayout -Component $plan -Client claude -TargetDirectory $emptyDirectoryLayout.ClaudeSkills -Method copy) 'empty-directory modification setup'
    $emptyDirectoryTarget = Join-Path $emptyDirectoryLayout.ClaudeSkills 'plan-and-build'
    New-Item -ItemType Directory -Path (Join-Path $emptyDirectoryTarget 'user-empty-directory') | Out-Null
    Assert-True (-not (Remove-ManagedComponent -Layout $emptyDirectoryLayout -Component $plan -Client claude -TargetDirectory $emptyDirectoryLayout.ClaudeSkills)) 'empty-directory modification is preserved'
    Assert-True (Test-Path -LiteralPath (Join-Path $emptyDirectoryTarget 'user-empty-directory')) 'user empty directory remains'

    # Failure after hook/settings removal restores all snapshots and permits retry.
    $retryRoot = Join-Path $temporaryRoot 'Removal Retry'
    New-Item -ItemType Directory -Path (Join-Path $retryRoot '.codex') -Force | Out-Null
    $retry = Get-InstallLayout -Scope global -Root $retryRoot
    [IO.File]::WriteAllText($retry.CodexConfig, "[features]`r`nhooks = false`r`n")
    Assert-True (Install-WorkflowHook -Layout $retry -Client codex -EnableCodexHooks) 'removal retry setup'
    (Get-Item -LiteralPath $retry.CodexConfig).IsReadOnly = $true
    $removeFailed = $false
    try { Remove-WorkflowHook -Layout $retry -Client codex | Out-Null } catch { $removeFailed = $true }
    Assert-True $removeFailed 'read-only config injects removal failure'
    Assert-True (Test-Path -LiteralPath (Join-Path $retry.CodexHooks 'claude-code-skills-workflow.ps1')) 'hook file restored after removal failure'
    Assert-True ((Get-Content -LiteralPath $retry.CodexHooksFile -Raw) -match 'commandWindows') 'hook JSON restored after removal failure'
    (Get-Item -LiteralPath $retry.CodexConfig).IsReadOnly = $false
    Assert-True (Remove-WorkflowHook -Layout $retry -Client codex) 'removal succeeds on retry'

    # General component manifest failures roll back target changes in both directions.
    $installFailureRoot = Join-Path $temporaryRoot 'Component Install Failure'
    New-Item -ItemType Directory -Path $installFailureRoot | Out-Null
    $installFailure = Get-InstallLayout -Scope project -Root $installFailureRoot
    $blockedManifestParent = Join-Path $installFailureRoot 'blocked-manifest-parent'
    [IO.File]::WriteAllText($blockedManifestParent, 'not a directory')
    $installFailure.ManifestDirectory = $blockedManifestParent
    $installFailure.Manifest = Join-Path $blockedManifestParent 'manifest.json'
    $componentInstallFailed = $false
    try { Install-ManagedComponent -Layout $installFailure -Component $plan -Client claude -TargetDirectory $installFailure.ClaudeSkills -Method copy | Out-Null } catch { $componentInstallFailed = $true }
    Assert-True $componentInstallFailed 'component manifest write failure injected'
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $installFailure.ClaudeSkills 'plan-and-build'))) 'failed component install removes unowned copy'

    $removeFailureRoot = Join-Path $temporaryRoot 'Component Remove Failure'
    New-Item -ItemType Directory -Path $removeFailureRoot | Out-Null
    $removeFailure = Get-InstallLayout -Scope project -Root $removeFailureRoot
    Assert-True (Install-ManagedComponent -Layout $removeFailure -Component $plan -Client claude -TargetDirectory $removeFailure.ClaudeSkills -Method copy) 'component removal failure setup'
    $manifestLock = [IO.File]::Open($removeFailure.Manifest, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    $componentRemoveFailed = $false
    try { Remove-ManagedComponent -Layout $removeFailure -Component $plan -Client claude -TargetDirectory $removeFailure.ClaudeSkills | Out-Null } catch { $componentRemoveFailed = $true }
    finally { $manifestLock.Dispose() }
    Assert-True $componentRemoveFailed 'component manifest prune failure injected'
    Assert-True (Test-Path -LiteralPath (Join-Path $removeFailure.ClaudeSkills 'plan-and-build')) 'failed removal restores component target'
    Assert-True (Test-Path -LiteralPath $removeFailure.Manifest) 'failed removal preserves manifest'
    Assert-True (Remove-ManagedComponent -Layout $removeFailure -Component $plan -Client claude -TargetDirectory $removeFailure.ClaudeSkills) 'component removal retry succeeds'

    # Backup cleanup failures happen after commit and never restore partial backups.
    $installCleanupRoot = Join-Path $temporaryRoot 'Install Backup Cleanup'
    New-Item -ItemType Directory -Path $installCleanupRoot | Out-Null
    $installCleanup = Get-InstallLayout -Scope project -Root $installCleanupRoot
    Assert-True (Install-ManagedComponent -Layout $installCleanup -Component $plan -Client claude -TargetDirectory $installCleanup.ClaudeSkills -Method copy) 'install cleanup setup'
    $installLockedFile = Join-Path $installCleanup.ClaudeSkills 'plan-and-build\SKILL.md'
    $installLock = [IO.File]::Open($installLockedFile, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    $lockedReinstallCommitted = $false
    try { $lockedReinstallCommitted = Install-ManagedComponent -Layout $installCleanup -Component $plan -Client claude -TargetDirectory $installCleanup.ClaudeSkills -Method copy }
    catch { $lockedReinstallCommitted = $false }
    finally { $installLock.Dispose() }
    Assert-True (Test-Path -LiteralPath (Join-Path $installCleanup.ClaudeSkills 'plan-and-build\SKILL.md')) 'reinstalled target remains complete'
    Assert-True (Test-Path -LiteralPath $installCleanup.Manifest) 'reinstalled target remains owned'
    $installCleanupManifest = Get-Content -LiteralPath $installCleanup.Manifest -Raw | ConvertFrom-Json
    $installCleanupHash = & (Get-Module Installer.Common) { Get-ContentHash -Path $args[0] } (Join-Path $installCleanup.ClaudeSkills 'plan-and-build')
    Assert-True ($installCleanupHash -eq @($installCleanupManifest.entries)[0].hash) 'locked reinstall leaves target and manifest consistent'

    $removeCleanupRoot = Join-Path $temporaryRoot 'Remove Backup Cleanup'
    New-Item -ItemType Directory -Path $removeCleanupRoot | Out-Null
    $removeCleanup = Get-InstallLayout -Scope project -Root $removeCleanupRoot
    Assert-True (Install-ManagedComponent -Layout $removeCleanup -Component $plan -Client claude -TargetDirectory $removeCleanup.ClaudeSkills -Method copy) 'remove cleanup setup'
    $removeLockedFile = Join-Path $removeCleanup.ClaudeSkills 'plan-and-build\SKILL.md'
    $removeLock = [IO.File]::Open($removeLockedFile, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    $lockedRemovalCommitted = $false
    try { $lockedRemovalCommitted = Remove-ManagedComponent -Layout $removeCleanup -Component $plan -Client claude -TargetDirectory $removeCleanup.ClaudeSkills }
    catch { $lockedRemovalCommitted = $false }
    finally { $removeLock.Dispose() }
    $removeTargetExists = Test-Path -LiteralPath (Join-Path $removeCleanup.ClaudeSkills 'plan-and-build')
    $removeManifestExists = Test-Path -LiteralPath $removeCleanup.Manifest
    Assert-True ($removeTargetExists -eq $removeManifestExists) 'locked removal never splits target and manifest state'
    if ($lockedRemovalCommitted) {
        Assert-True (-not $removeTargetExists) 'committed removal does not restore a partial backup'
    } else {
        $removeCleanupManifest = Get-Content -LiteralPath $removeCleanup.Manifest -Raw | ConvertFrom-Json
        $removeCleanupHash = & (Get-Module Installer.Common) { Get-ContentHash -Path $args[0] } (Join-Path $removeCleanup.ClaudeSkills 'plan-and-build')
        Assert-True ($removeCleanupHash -eq @($removeCleanupManifest.entries)[0].hash) 'failed locked removal restores a complete target'
    }

    # The Windows reminder hook must stay far below its registered 5 second UserPromptSubmit timeout;
    # a run that reaches it is cut off and the reminder vanishes with no error anywhere. Cold process
    # start is the measured cost, so every sample spawns a new interpreter the way the installed
    # command does: powershell.exe -NoProfile -ExecutionPolicy Bypass -File <hook>. A hook that stops
    # responding is killed at the limit and reported as a failure, never waited on indefinitely.
    $isNativeWindows = ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT)
    $hookHostPath = if ($isNativeWindows) { Get-WorkflowHookHostPath } else { $null }
    if (-not $isNativeWindows) {
        Write-Host 'Workflow hook performance section skipped: not native Windows.' -ForegroundColor Yellow
    } elseif ([string]::IsNullOrEmpty($hookHostPath)) {
        Write-Host 'Workflow hook performance section skipped: neither powershell.exe nor pwsh is available.' -ForegroundColor Yellow
    } else {
        $hookComponents = @(Get-SupportedComponents -Client claude -Platform windows -Kind hook | Where-Object { $_.name -eq 'workflow-reminder' })
        Assert-True ($hookComponents.Count -eq 1) 'catalog declares one Windows reminder hook component'
        $hookScript = & (Get-Module Installer.Common) { Resolve-ComponentSource -Component $args[0] -Client $args[1] } $hookComponents[0] claude
        Assert-True (Test-Path -LiteralPath $hookScript -PathType Leaf) 'Windows reminder hook script exists'
        # This prompt fires the plan reminder, so the run walks the full regex set (near worst case).
        $hookPayloadBytes = $utf8.GetBytes('{"prompt":"새 인증 기능을 구현해줘"}')

        # Two tiers. The hard limit is the timeout the installer registers: a run at or past it is
        # truncated in real use, so the reminder silently disappears. It binds every run, cold start
        # included, because a user's first prompt in a session is exactly that cold run. The warm
        # budget is half the hard limit and guards the margin; it is applied to the warm median
        # rather than the cold run or the warm max, because cold start and single warm outliers swing
        # with disk cache and antivirus scanning on shared runners and would only make this flaky.
        $hookHardLimitSeconds = 5.0
        $hookWarmBudgetSeconds = 2.5

        $coldRun = Invoke-WorkflowHookProcess -HostPath $hookHostPath -HookPath $hookScript -PayloadBytes $hookPayloadBytes -Encoding $utf8 -TimeoutSeconds $hookHardLimitSeconds
        Assert-WorkflowHookRun -Result $coldRun -Label 'cold reminder hook run (first prompt of a session)' -HardLimitSeconds $hookHardLimitSeconds
        Write-Host ('Reminder hook cold run: {0:N3}s (hard limit {1:N1}s).' -f $coldRun.Seconds, $hookHardLimitSeconds) -ForegroundColor Cyan

        $hookSamples = @()
        for ($sampleIndex = 1; $sampleIndex -le 5; $sampleIndex++) {
            $sample = Invoke-WorkflowHookProcess -HostPath $hookHostPath -HookPath $hookScript -PayloadBytes $hookPayloadBytes -Encoding $utf8 -TimeoutSeconds $hookHardLimitSeconds
            Assert-WorkflowHookRun -Result $sample -Label "warm reminder hook run $sampleIndex" -HardLimitSeconds $hookHardLimitSeconds
            $hookSamples += [double]$sample.Seconds
        }
        $sortedSamples = @($hookSamples | Sort-Object)
        $medianSeconds = [double]$sortedSamples[[int]([math]::Floor($sortedSamples.Count / 2))]
        $maximumSeconds = [double]$sortedSamples[$sortedSamples.Count - 1]
        Write-Host ('Reminder hook warm runs: median {0:N3}s, max {1:N3}s over {2} samples (warm budget {3:N1}s).' -f $medianSeconds, $maximumSeconds, $sortedSamples.Count, $hookWarmBudgetSeconds) -ForegroundColor Cyan
        Assert-True ($medianSeconds -lt $hookWarmBudgetSeconds) ("reminder hook warm median stays under {0:N1}s (median {1:N3}s, warm max {2:N3}s, cold {3:N3}s, hard limit {4:N1}s)" -f $hookWarmBudgetSeconds, $medianSeconds, $maximumSeconds, $coldRun.Seconds, $hookHardLimitSeconds)
    }

    Write-Host 'Windows installer integration tests passed.' -ForegroundColor Green
} finally {
    Remove-Item -LiteralPath $temporaryRoot -Recurse -Force -ErrorAction SilentlyContinue
}
