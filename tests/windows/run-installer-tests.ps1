$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8

$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Import-Module (Join-Path $root 'scripts\Installer.Common.psm1') -Force

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw "Assertion failed: $Message" }
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

    Write-Host 'Windows installer integration tests passed.' -ForegroundColor Green
} finally {
    Remove-Item -LiteralPath $temporaryRoot -Recurse -Force -ErrorAction SilentlyContinue
}
