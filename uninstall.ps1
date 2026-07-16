# Native Windows uninstaller for Claude Desktop Code and Codex.
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
    param([string]$Prompt, [bool]$Default = $false)
    $suffix = if ($Default) { '[Y/n]' } else { '[y/N]' }
    $answer = (Read-Host "$Prompt $suffix").Trim()
    if ([string]::IsNullOrEmpty($answer)) { return $Default }
    return $answer -match '^[Yy]$'
}

if ($env:OS -ne 'Windows_NT') {
    throw 'uninstall.ps1 supports native Windows PowerShell only. Run bash uninstall.sh inside WSL/Linux.'
}

Write-Host 'Team AI skills, agents, and hooks - Windows native uninstaller' -ForegroundColor Cyan
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

if (-not (Read-YesNo "Remove repository-owned components from $root?" $false)) {
    Write-Host 'Nothing removed.'
    exit 0
}

try {
    foreach ($client in $clients) {
        $skillDirectory = if ($client -eq 'claude') { $layout.ClaudeSkills } else { $layout.CodexSkills }
        foreach ($component in Get-SupportedComponents -Client $client -Platform windows -Kind skill) {
            Remove-ManagedComponent -Layout $layout -Component $component -Client $client -TargetDirectory $skillDirectory | Out-Null
        }
        $agentDirectory = if ($client -eq 'claude') { $layout.ClaudeAgents } else { $layout.CodexAgents }
        foreach ($component in Get-SupportedComponents -Client $client -Platform windows -Kind agent) {
            Remove-ManagedComponent -Layout $layout -Component $component -Client $client -TargetDirectory $agentDirectory | Out-Null
        }
        if ($scope -eq 'global' -and (Read-YesNo "Remove the managed $client workflow hook?" $false)) {
            Remove-WorkflowHook -Layout $layout -Client $client
        }
    }
} catch {
    Write-Error "Uninstall stopped: $($_.Exception.Message)"
    exit 1
}

Write-Host 'Uninstall complete. Modified, foreign, and unverified items were preserved.' -ForegroundColor Green
