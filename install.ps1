# Native Windows installer for Claude Desktop Code and Codex.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$catalogPath = Join-Path $PSScriptRoot 'components.json'
if (-not (Test-Path -LiteralPath $catalogPath -PathType Leaf)) { throw "components.json not found: $catalogPath" }
Import-Module (Join-Path $PSScriptRoot 'scripts\Installer.Common.psm1') -Force

function Read-MenuChoice {
    param([string]$Prompt, [string[]]$Allowed)
    while ($true) {
        $choice = (Read-Host $Prompt).Trim()
        if ($Allowed -contains $choice) { return $choice }
        Write-Warning "Choose one of: $($Allowed -join ', ')"
    }
}

function Read-YesNo {
    param([string]$Prompt, [bool]$Default = $true)
    $suffix = if ($Default) { '[Y/n]' } else { '[y/N]' }
    $answer = (Read-Host "$Prompt $suffix").Trim()
    if ([string]::IsNullOrEmpty($answer)) { return $Default }
    return $answer -match '^[Yy]$'
}

if ($env:OS -ne 'Windows_NT') {
    throw 'install.ps1 supports native Windows PowerShell only. Run bash install.sh inside WSL/Linux.'
}

Write-Host 'Team AI skills, agents, and hooks - Windows native installer' -ForegroundColor Cyan
Write-Host '1) Claude Desktop Code  2) Codex  3) Both'
$clientChoice = Read-MenuChoice 'Clients' @('1', '2', '3')
$clients = @()
if ($clientChoice -in @('1', '3')) { $clients += 'claude' }
if ($clientChoice -in @('2', '3')) { $clients += 'codex' }

Write-Host "`n1) Global (%USERPROFILE%)  2) Project"
$scopeChoice = Read-MenuChoice 'Scope' @('1', '2')
if ($scopeChoice -eq '1') {
    $scope = 'global'
    $root = $env:USERPROFILE
} else {
    $scope = 'project'
    $inputPath = Read-Host "Project path [$((Get-Location).Path)]"
    if ([string]::IsNullOrWhiteSpace($inputPath)) { $inputPath = (Get-Location).Path }
    $root = (Resolve-Path -LiteralPath $inputPath).Path
}
$layout = Get-InstallLayout -Scope $scope -Root $root

$skillMethod = 'copy'
if (Test-SymbolicLinkEligible -Layout $layout) {
    Write-Host "`nSkill mode: 1) Copy (recommended)  2) Symbolic link (local Windows paths only)"
    if ((Read-MenuChoice 'Mode' @('1', '2')) -eq '2') { $skillMethod = 'symlink' }
} else {
    Write-Host 'Skill mode: copy (links are unavailable for UNC/WSL paths).' -ForegroundColor Yellow
}

$claudeSkillsExisted = Test-Path -LiteralPath $layout.ClaudeSkills -PathType Container
$claudeAgentsExisted = Test-Path -LiteralPath $layout.ClaudeAgents -PathType Container
$codexHookInstalled = $false

try {
    foreach ($client in $clients) {
        if ($client -eq 'codex') { Invoke-LegacyCodexSkillMigration -Layout $layout }
        $skillDirectory = if ($client -eq 'claude') { $layout.ClaudeSkills } else { $layout.CodexSkills }
        foreach ($component in Get-SupportedComponents -Client $client -Platform windows -Kind skill) {
            Install-ManagedComponent -Layout $layout -Component $component -Client $client -TargetDirectory $skillDirectory -Method $skillMethod | Out-Null
        }

        $agentDirectory = if ($client -eq 'claude') { $layout.ClaudeAgents } else { $layout.CodexAgents }
        foreach ($component in Get-SupportedComponents -Client $client -Platform windows -Kind agent) {
            Install-ManagedComponent -Layout $layout -Component $component -Client $client -TargetDirectory $agentDirectory -Method copy | Out-Null
        }
    }

    if ($scope -eq 'global') {
        foreach ($client in $clients) {
            if (-not (Read-YesNo "Install the $client UserPromptSubmit workflow hook?" $true)) { continue }
            if ($client -eq 'codex' -and (Test-CodexInlineHooks -Path $layout.CodexConfig)) {
                Write-Warning 'Inline Codex hooks already exist in config.toml.'
                if (-not (Read-YesNo 'Also install hooks.json workflow hook?' $false)) { continue }
            }
            $enable = $false
            if ($client -eq 'codex') {
                $state = Get-CodexHookFeatureState -Path $layout.CodexConfig
                if ($state.Value -eq $false) {
                    $enable = Read-YesNo 'Codex hooks are disabled. Enable them for this install?' $false
                    if (-not $enable) { Write-Warning 'Skipping Codex hook because hooks remain disabled.'; continue }
                }
            }
            $hookInstalled = Install-WorkflowHook -Layout $layout -Client $client -EnableCodexHooks:$enable
            if ($client -eq 'codex' -and $hookInstalled) { $codexHookInstalled = $true }
        }
    } else {
        Write-Host 'Project scope installs skills and agents only; Windows hooks are global-only.' -ForegroundColor Yellow
    }
} catch {
    Write-Error "Installation stopped: $($_.Exception.Message)"
    exit 1
}

Show-DependencyDiagnostics
Write-Host "`nInstallation complete." -ForegroundColor Green
if ($clients -contains 'claude' -and ((-not $claudeSkillsExisted -and (Test-Path $layout.ClaudeSkills)) -or (-not $claudeAgentsExisted -and (Test-Path $layout.ClaudeAgents)))) {
    Write-Host 'Restart Claude Desktop once because a skills/agents directory was created.' -ForegroundColor Yellow
}
if ($codexHookInstalled) {
    Write-Host 'Start a new Codex session, open /hooks, review the hook, and approve trust.' -ForegroundColor Yellow
}
Write-Host 'Manual checks: Codex /skills, agents, /hooks; Claude Desktop Code skills, agents, and hook behavior.'
