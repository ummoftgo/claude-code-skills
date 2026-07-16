Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$script:RepositoryRoot = Split-Path -Parent $PSScriptRoot
$script:CatalogPath = Join-Path $script:RepositoryRoot 'components.json'
$script:Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Get-RepositoryRoot { return $script:RepositoryRoot }

function Get-ComponentCatalog {
    if (-not (Test-Path -LiteralPath $script:CatalogPath -PathType Leaf)) {
        throw "Component catalog not found: $script:CatalogPath"
    }
    $catalog = Get-Content -LiteralPath $script:CatalogPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($catalog.version -ne 1 -or $null -eq $catalog.components) {
        throw "Unsupported component catalog: $script:CatalogPath"
    }
    return @($catalog.components)
}

function Get-SupportedComponents {
    param(
        [Parameter(Mandatory = $true)][ValidateSet('claude', 'codex')][string]$Client,
        [Parameter(Mandatory = $true)][ValidateSet('posix', 'windows')][string]$Platform,
        [ValidateSet('skill', 'agent', 'hook')][string]$Kind
    )
    return @(Get-ComponentCatalog | Where-Object {
        $support = $_.support.$Client.$Platform
        $kindMatches = [string]::IsNullOrEmpty($Kind) -or $_.kind -eq $Kind
        $support -eq $true -and $kindMatches
    })
}

function Resolve-ComponentSource {
    param([Parameter(Mandatory = $true)]$Component, [Parameter(Mandatory = $true)][string]$Client)
    $source = $Component.source
    if ($source -is [string]) {
        $relative = $source
    } elseif ($Component.kind -eq 'agent') {
        $relative = $source.$Client
    } else {
        $relative = $source.windows
    }
    if ([string]::IsNullOrWhiteSpace($relative)) {
        throw "No source for $($Component.name) ($Client)"
    }
    return [IO.Path]::GetFullPath((Join-Path $script:RepositoryRoot $relative))
}

function Get-InstallLayout {
    param(
        [Parameter(Mandatory = $true)][ValidateSet('global', 'project')][string]$Scope,
        [Parameter(Mandatory = $true)][string]$Root
    )
    $resolvedRoot = [IO.Path]::GetFullPath($Root)
    return [pscustomobject][ordered]@{
        Scope = $Scope
        Root = $resolvedRoot
        ManifestDirectory = Join-Path $resolvedRoot '.claude-code-skills'
        Manifest = Join-Path $resolvedRoot '.claude-code-skills\manifest.json'
        LegacyManifest = Join-Path $resolvedRoot '.claude-code-skills\manifest.tsv'
        ClaudeSkills = Join-Path $resolvedRoot '.claude\skills'
        ClaudeAgents = Join-Path $resolvedRoot '.claude\agents'
        ClaudeHooks = Join-Path $resolvedRoot '.claude\hooks'
        ClaudeSettings = Join-Path $resolvedRoot '.claude\settings.json'
        CodexSkills = Join-Path $resolvedRoot '.agents\skills'
        CodexAgents = Join-Path $resolvedRoot '.codex\agents'
        CodexHooks = Join-Path $resolvedRoot '.codex\hooks'
        CodexHooksFile = Join-Path $resolvedRoot '.codex\hooks.json'
        CodexConfig = Join-Path $resolvedRoot '.codex\config.toml'
        LegacyCodexSkills = Join-Path $resolvedRoot '.codex\skills\local'
    }
}

function Test-PathInside {
    param([string]$Path, [string]$Root)
    $fullPath = [IO.Path]::GetFullPath($Path).TrimEnd('\')
    $fullRoot = [IO.Path]::GetFullPath($Root).TrimEnd('\')
    return $fullPath.Equals($fullRoot, [StringComparison]::OrdinalIgnoreCase) -or
        $fullPath.StartsWith($fullRoot + '\', [StringComparison]::OrdinalIgnoreCase)
}

function Assert-SafeTarget {
    param([string]$Target, [string]$Root)
    if (-not (Test-PathInside $Target $Root) -or
        [IO.Path]::GetFullPath($Target).TrimEnd('\').Equals([IO.Path]::GetFullPath($Root).TrimEnd('\'), [StringComparison]::OrdinalIgnoreCase)) {
        throw "Target is outside the selected scope: $Target"
    }
}

function Get-ContentHash {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    $item = Get-Item -LiteralPath $Path -Force
    if (-not $item.PSIsContainer) {
        return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    }

    $lines = New-Object System.Collections.Generic.List[string]
    Get-ChildItem -LiteralPath $Path -Recurse -Force | Sort-Object {
        $_.FullName.Substring($item.FullName.TrimEnd('\').Length).TrimStart('\').Replace('\', '/')
    } | ForEach-Object {
        $relative = $_.FullName.Substring($item.FullName.TrimEnd('\').Length).TrimStart('\').Replace('\', '/')
        if ($_.PSIsContainer) {
            $lines.Add("D`t$relative")
        } else {
            $fileHash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            $lines.Add("F`t$relative`t$fileHash")
        }
    }
    $bytes = $script:Utf8NoBom.GetBytes(($lines -join "`n"))
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant()
    } finally {
        $sha.Dispose()
    }
}

function Get-LegacyPosixContentHash {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    $item = Get-Item -LiteralPath $Path -Force
    if (-not $item.PSIsContainer) {
        return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $lines = New-Object System.Collections.Generic.List[string]
    Get-ChildItem -LiteralPath $Path -File -Recurse -Force | Sort-Object {
        $_.FullName.Substring($item.FullName.TrimEnd('\').Length).TrimStart('\').Replace('\', '/')
    } | ForEach-Object {
        $relative = $_.FullName.Substring($item.FullName.TrimEnd('\').Length).TrimStart('\').Replace('\', '/')
        $fileHash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        $lines.Add("$fileHash  ./$relative")
    }
    $bytes = $script:Utf8NoBom.GetBytes(($lines -join "`n") + $(if ($lines.Count -gt 0) { "`n" } else { '' }))
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant()
    } finally {
        $sha.Dispose()
    }
}

function Move-ItemWithRetry {
    param([string]$Source, [string]$Destination, [switch]$Force)
    for ($attempt = 1; $attempt -le 5; $attempt++) {
        try {
            $parameters = @{ LiteralPath = $Source; Destination = $Destination; ErrorAction = 'Stop' }
            if ($Force) { $parameters.Force = $true }
            $sourceItem = Get-Item -LiteralPath $Source -Force -ErrorAction Stop
            if ($sourceItem.PSIsContainer -and -not (Test-Path -LiteralPath $Destination)) {
                [IO.Directory]::Move($sourceItem.FullName, [IO.Path]::GetFullPath($Destination))
            } else {
                Move-Item @parameters
            }
            return
        } catch {
            if ($attempt -eq 5) { throw }
            Start-Sleep -Milliseconds (50 * $attempt)
        }
    }
}

function Read-Manifest {
    param([Parameter(Mandatory = $true)]$Layout)
    if (Test-Path -LiteralPath $Layout.Manifest -PathType Leaf) {
        $data = Get-Content -LiteralPath $Layout.Manifest -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($data.version -ne 2 -or $null -eq $data.entries) { throw "Unsupported manifest: $($Layout.Manifest)" }
        return $data
    }

    $data = [pscustomobject][ordered]@{ version = 2; entries = @() }
    if (Test-Path -LiteralPath $Layout.LegacyManifest -PathType Leaf) {
        $entries = New-Object System.Collections.Generic.List[object]
        Get-Content -LiteralPath $Layout.LegacyManifest -Encoding UTF8 | ForEach-Object {
            if ([string]::IsNullOrWhiteSpace($_) -or $_.StartsWith('#')) { return }
            $fields = $_ -split "`t"
            if ($fields.Count -lt 6) { return }
            $typeParts = $fields[0] -split '-', 2
            if ($typeParts.Count -ne 2) { return }
            $kind = $typeParts[1]
            $component = Split-Path -Leaf $fields[1]
            if ($kind -eq 'agent') { $component = [IO.Path]::GetFileNameWithoutExtension($component) }
            if ($kind -eq 'hook') { $component = 'workflow-reminder' }
            $entries.Add([pscustomobject][ordered]@{
                platform = 'posix'; scope = $Layout.Scope; client = $typeParts[0]; kind = $kind
                component = $component; target = $fields[1]; method = $fields[2]
                source = $fields[3]; hash = $fields[4]; installedAt = $fields[5]; importedFrom = 'v1'
            })
        }
        $data.entries = [object[]]$entries.ToArray()
        if (@($data.entries).Count -gt 0) { Write-Manifest -Layout $Layout -Data $data }
    }
    return $data
}

function Write-Manifest {
    param([Parameter(Mandatory = $true)]$Layout, [Parameter(Mandatory = $true)]$Data)
    if (-not (Test-Path -LiteralPath $Layout.ManifestDirectory)) {
        New-Item -ItemType Directory -Path $Layout.ManifestDirectory -Force | Out-Null
    }
    $temporary = Join-Path $Layout.ManifestDirectory ('.manifest.' + [guid]::NewGuid().ToString('N') + '.tmp')
    try {
        $json = $Data | ConvertTo-Json -Depth 12
        [IO.File]::WriteAllText($temporary, $json + "`n", $script:Utf8NoBom)
        Move-ItemWithRetry -Source $temporary -Destination $Layout.Manifest -Force
    } finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
    }
}

function Get-ManifestEntry {
    param([Parameter(Mandatory = $true)]$Layout, [Parameter(Mandatory = $true)][string]$Target)
    $full = [IO.Path]::GetFullPath($Target)
    $manifest = Read-Manifest -Layout $Layout
    return @($manifest.entries) | Where-Object {
        [IO.Path]::GetFullPath([string]$_.target).Equals($full, [StringComparison]::OrdinalIgnoreCase)
    } | Select-Object -First 1
}

function Save-ManifestEntry {
    param(
        [Parameter(Mandatory = $true)]$Layout,
        [Parameter(Mandatory = $true)][string]$Client,
        [Parameter(Mandatory = $true)][string]$Kind,
        [Parameter(Mandatory = $true)][string]$Component,
        [Parameter(Mandatory = $true)][string]$Target,
        [Parameter(Mandatory = $true)][string]$Method,
        [Parameter(Mandatory = $true)][string]$Source,
        [string]$Hash,
        [string]$ConfigurationKey,
        $ConfigurationBefore,
        $ConfigurationAfter
    )
    $data = Read-Manifest -Layout $Layout
    $full = [IO.Path]::GetFullPath($Target)
    $data.entries = @($data.entries | Where-Object {
        -not [IO.Path]::GetFullPath([string]$_.target).Equals($full, [StringComparison]::OrdinalIgnoreCase)
    })
    $entry = [pscustomobject][ordered]@{
        platform = 'windows'; scope = $Layout.Scope; client = $Client; kind = $Kind
        component = $Component; target = $full; method = $Method; source = $Source
        hash = $Hash; installedAt = [DateTime]::UtcNow.ToString('o')
    }
    if (-not [string]::IsNullOrWhiteSpace($ConfigurationKey)) {
        $entry | Add-Member -NotePropertyName configuration -NotePropertyValue ([pscustomobject][ordered]@{
            key = $ConfigurationKey; before = $ConfigurationBefore; after = $ConfigurationAfter
        })
    }
    $data.entries = @($data.entries) + @($entry)
    Write-Manifest -Layout $Layout -Data $data
    return $entry
}

function Remove-ManifestEntry {
    param([Parameter(Mandatory = $true)]$Layout, [Parameter(Mandatory = $true)][string]$Target)
    $data = Read-Manifest -Layout $Layout
    $full = [IO.Path]::GetFullPath($Target)
    $data.entries = @($data.entries | Where-Object {
        -not [IO.Path]::GetFullPath([string]$_.target).Equals($full, [StringComparison]::OrdinalIgnoreCase)
    })
    if ($data.entries.Count -eq 0) {
        if (Test-Path -LiteralPath $Layout.Manifest) { Remove-Item -LiteralPath $Layout.Manifest -Force }
        if (Test-Path -LiteralPath $Layout.ManifestDirectory) {
            Remove-Item -LiteralPath $Layout.ManifestDirectory -Force -ErrorAction SilentlyContinue
        }
    } else {
        Write-Manifest -Layout $Layout -Data $data
    }
}

function Get-LinkTargetPath {
    param([string]$Path)
    try {
        $item = Get-Item -LiteralPath $Path -Force
        if ($item.LinkType -ne 'SymbolicLink' -or $null -eq $item.Target) { return $null }
        $target = [string](@($item.Target)[0])
        if (-not [IO.Path]::IsPathRooted($target)) { $target = Join-Path (Split-Path -Parent $item.FullName) $target }
        return [IO.Path]::GetFullPath($target)
    } catch { return $null }
}

function Test-ManagedTarget {
    param([string]$Target, $Entry, [switch]$AllowRepositoryLinkWithoutManifest)
    if (-not (Test-Path -LiteralPath $Target)) { return $false }
    $linkTarget = Get-LinkTargetPath -Path $Target
    if ($null -ne $linkTarget -and (Test-PathInside $linkTarget $script:RepositoryRoot)) {
        return $AllowRepositoryLinkWithoutManifest -or $null -ne $Entry
    }
    if ($null -eq $Entry -or [string]::IsNullOrWhiteSpace([string]$Entry.hash) -or $Entry.hash -eq '-') { return $false }
    $isPosix = (($null -ne $Entry.PSObject.Properties['platform']) -and $Entry.platform -eq 'posix') -or
        (($null -ne $Entry.PSObject.Properties['importedFrom']) -and $Entry.importedFrom -eq 'v1')
    if ($isPosix) { $current = Get-LegacyPosixContentHash -Path $Target }
    else { $current = Get-ContentHash -Path $Target }
    return $null -ne $current -and $current.Equals([string]$Entry.hash, [StringComparison]::OrdinalIgnoreCase)
}

function Test-SymbolicLinkEligible {
    param([Parameter(Mandatory = $true)]$Layout)
    $repo = [IO.Path]::GetFullPath($script:RepositoryRoot)
    if ($repo.StartsWith('\\') -or $Layout.Root.StartsWith('\\') -or -not (Test-Path -LiteralPath $repo -PathType Container)) {
        return $false
    }
    try {
        $repoDrive = New-Object -TypeName IO.DriveInfo -ArgumentList ([IO.Path]::GetPathRoot($repo))
        $targetDrive = New-Object -TypeName IO.DriveInfo -ArgumentList ([IO.Path]::GetPathRoot([IO.Path]::GetFullPath($Layout.Root)))
        return $repoDrive.DriveType -eq [IO.DriveType]::Fixed -and $targetDrive.DriveType -eq [IO.DriveType]::Fixed
    } catch {
        return $false
    }
}

function Copy-WithRollback {
    param([string]$Source, [string]$Target)
    $parent = Split-Path -Parent $Target
    if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    $staging = Join-Path $parent ('.install.' + [guid]::NewGuid().ToString('N'))
    $backup = Join-Path $parent ('.backup.' + [guid]::NewGuid().ToString('N'))
    $hadTarget = Test-Path -LiteralPath $Target
    try {
        if ((Get-Item -LiteralPath $Source).PSIsContainer) {
            Copy-Item -LiteralPath $Source -Destination $staging -Recurse -Force
        } else {
            Copy-Item -LiteralPath $Source -Destination $staging -Force
        }
        if ($hadTarget) { Move-ItemWithRetry -Source $Target -Destination $backup }
        Move-ItemWithRetry -Source $staging -Destination $Target
        if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Recurse -Force }
    } catch {
        if (Test-Path -LiteralPath $staging) { Remove-Item -LiteralPath $staging -Recurse -Force }
        if (Test-Path -LiteralPath $backup) {
            if (Test-Path -LiteralPath $Target) { Remove-Item -LiteralPath $Target -Recurse -Force }
            Move-ItemWithRetry -Source $backup -Destination $Target
        }
        throw
    }
}

function Install-ManagedComponent {
    param(
        [Parameter(Mandatory = $true)]$Layout,
        [Parameter(Mandatory = $true)]$Component,
        [Parameter(Mandatory = $true)][ValidateSet('claude', 'codex')][string]$Client,
        [Parameter(Mandatory = $true)][string]$TargetDirectory,
        [ValidateSet('copy', 'symlink')][string]$Method = 'copy'
    )
    $source = Resolve-ComponentSource -Component $Component -Client $Client
    $extension = ''
    if ($Component.kind -eq 'agent') { if ($Client -eq 'claude') { $extension = '.md' } else { $extension = '.toml' } }
    $target = Join-Path $TargetDirectory ($Component.name + $extension)
    Assert-SafeTarget -Target $target -Root $Layout.Root
    $entry = Get-ManifestEntry -Layout $Layout -Target $target
    if (Test-Path -LiteralPath $target) {
        if (-not (Test-ManagedTarget -Target $target -Entry $entry)) {
            Write-Warning "Preserving unverified or modified item: $target"
            return $false
        }
    }
    if (-not (Test-Path -LiteralPath $TargetDirectory)) { New-Item -ItemType Directory -Path $TargetDirectory -Force | Out-Null }

    if ($Component.kind -ne 'skill') { $Method = 'copy' }
    if ($Method -eq 'symlink' -and -not (Test-SymbolicLinkEligible -Layout $Layout)) { $Method = 'copy' }
    $staging = Join-Path $TargetDirectory ('.install.' + [guid]::NewGuid().ToString('N'))
    $backup = Join-Path $TargetDirectory ('.backup.' + [guid]::NewGuid().ToString('N'))
    $manifestSnapshot = Get-FileSnapshot -Path $Layout.Manifest
    $hadTarget = Test-Path -LiteralPath $target
    $targetMovedToBackup = $false
    $newTargetActivated = $false
    try {
        if ($Method -eq 'symlink') {
            try {
                New-Item -ItemType SymbolicLink -Path $staging -Target $source | Out-Null
            } catch {
                if (Test-Path -LiteralPath $staging) { Remove-Item -LiteralPath $staging -Recurse -Force }
                Write-Warning "Symbolic link creation failed; falling back to copy: $($_.Exception.Message)"
                if ((Get-Item -LiteralPath $source).PSIsContainer) { Copy-Item -LiteralPath $source -Destination $staging -Recurse -Force }
                else { Copy-Item -LiteralPath $source -Destination $staging -Force }
                $Method = 'copy'
            }
        } elseif ((Get-Item -LiteralPath $source).PSIsContainer) {
            Copy-Item -LiteralPath $source -Destination $staging -Recurse -Force
        } else {
            Copy-Item -LiteralPath $source -Destination $staging -Force
        }

        if ($hadTarget) {
            Move-ItemWithRetry -Source $target -Destination $backup
            $targetMovedToBackup = $true
        }
        Move-ItemWithRetry -Source $staging -Destination $target
        $newTargetActivated = $true
        $hash = '-'
        if ($Method -eq 'copy') { $hash = Get-ContentHash -Path $target }
        Save-ManifestEntry -Layout $Layout -Client $Client -Kind $Component.kind -Component $Component.name -Target $target -Method $Method -Source $source -Hash $hash | Out-Null
    } catch {
        $originalError = $_
        try { if ($newTargetActivated -and (Test-Path -LiteralPath $target)) { Remove-Item -LiteralPath $target -Recurse -Force } } catch { Write-Warning "Rollback could not remove partial target ${target}: $($_.Exception.Message)" }
        try { if ($targetMovedToBackup -and (Test-Path -LiteralPath $backup)) { Move-ItemWithRetry -Source $backup -Destination $target } } catch { Write-Warning "Rollback could not restore target ${target}: $($_.Exception.Message)" }
        Restore-SnapshotsBestEffort @([pscustomobject]@{ Path = $Layout.Manifest; Snapshot = $manifestSnapshot })
        try { if (Test-Path -LiteralPath $staging) { Remove-Item -LiteralPath $staging -Recurse -Force } } catch { Write-Warning "Rollback could not remove staging path ${staging}: $($_.Exception.Message)" }
        throw $originalError
    }
    try { if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Recurse -Force } } catch { Write-Warning "Installed component is consistent, but its old backup could not be fully removed: $backup" }
    Write-Host "[OK] $($Component.name) -> $target ($Method)" -ForegroundColor Green
    return $true
}

function Remove-ManagedComponent {
    param(
        [Parameter(Mandatory = $true)]$Layout,
        [Parameter(Mandatory = $true)]$Component,
        [Parameter(Mandatory = $true)][string]$Client,
        [Parameter(Mandatory = $true)][string]$TargetDirectory
    )
    $extension = ''
    if ($Component.kind -eq 'agent') { if ($Client -eq 'claude') { $extension = '.md' } else { $extension = '.toml' } }
    $target = Join-Path $TargetDirectory ($Component.name + $extension)
    if (-not (Test-Path -LiteralPath $target)) { return $false }
    Assert-SafeTarget -Target $target -Root $Layout.Root
    $entry = Get-ManifestEntry -Layout $Layout -Target $target
    if (-not (Test-ManagedTarget -Target $target -Entry $entry)) {
        Write-Warning "Preserving unverified or modified item: $target"
        return $false
    }
    $backup = Join-Path $TargetDirectory ('.remove.' + [guid]::NewGuid().ToString('N'))
    $manifestSnapshot = Get-FileSnapshot -Path $Layout.Manifest
    $targetMovedToBackup = $false
    try {
        Move-ItemWithRetry -Source $target -Destination $backup
        $targetMovedToBackup = $true
        Remove-ManifestEntry -Layout $Layout -Target $target
    } catch {
        $originalError = $_
        try {
            if ($targetMovedToBackup -and (Test-Path -LiteralPath $backup)) {
                if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Recurse -Force }
                Move-ItemWithRetry -Source $backup -Destination $target
            }
        } catch { Write-Warning "Rollback could not restore removed target ${target}: $($_.Exception.Message)" }
        Restore-SnapshotsBestEffort @([pscustomobject]@{ Path = $Layout.Manifest; Snapshot = $manifestSnapshot })
        throw $originalError
    }
    try { if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Recurse -Force } } catch { Write-Warning "Component removal is committed, but its backup could not be fully removed: $backup" }
    Write-Host "[REMOVED] $target" -ForegroundColor Yellow
    return $true
}

function Invoke-LegacyCodexSkillMigration {
    param([Parameter(Mandatory = $true)]$Layout)
    if ($Layout.Scope -ne 'global' -or -not (Test-Path -LiteralPath $Layout.LegacyCodexSkills -PathType Container)) { return }
    foreach ($component in Get-SupportedComponents -Client codex -Platform windows -Kind skill) {
        $legacy = Join-Path $Layout.LegacyCodexSkills $component.name
        $target = Join-Path $Layout.CodexSkills $component.name
        if (-not (Test-Path -LiteralPath $legacy)) { continue }
        if (Test-Path -LiteralPath $target) {
            Write-Warning "Legacy migration collision; preserving both locations: $($component.name)"
            continue
        }
        $entry = Get-ManifestEntry -Layout $Layout -Target $legacy
        if (-not (Test-ManagedTarget -Target $legacy -Entry $entry -AllowRepositoryLinkWithoutManifest)) {
            Write-Warning "Legacy skill ownership is unverified; preserving: $legacy"
            continue
        }
        if (-not (Test-Path -LiteralPath $Layout.CodexSkills)) { New-Item -ItemType Directory -Path $Layout.CodexSkills -Force | Out-Null }
        Copy-WithRollback -Source $legacy -Target $target
        $source = Resolve-ComponentSource -Component $component -Client codex
        try {
            Save-ManifestEntry -Layout $Layout -Client codex -Kind skill -Component $component.name -Target $target -Method copy -Source $source -Hash (Get-ContentHash $target) | Out-Null
        } catch {
            if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction SilentlyContinue }
            throw
        }
        Remove-Item -LiteralPath $legacy -Recurse -Force
        if ($null -ne $entry) { Remove-ManifestEntry -Layout $Layout -Target $legacy }
        Write-Host "[MIGRATED] $legacy -> $target" -ForegroundColor Green
    }
}

function Read-JsonObject {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return [pscustomobject]@{} }
    $raw = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
    if ([string]::IsNullOrWhiteSpace($raw)) { return [pscustomobject]@{} }
    $data = $raw | ConvertFrom-Json
    if ($null -eq $data -or $data -is [System.Array]) { throw "Top-level JSON value must be an object: $Path" }
    return $data
}

function Set-ObjectProperty {
    param($Object, [string]$Name, $Value)
    if ($null -ne $Object.PSObject.Properties[$Name]) { $Object.$Name = $Value }
    else { $Object | Add-Member -NotePropertyName $Name -NotePropertyValue $Value }
}

function Write-JsonObject {
    param([string]$Path, $Data)
    $parent = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    $temporary = Join-Path $parent ('.json.' + [guid]::NewGuid().ToString('N') + '.tmp')
    try {
        [IO.File]::WriteAllText($temporary, ($Data | ConvertTo-Json -Depth 20) + "`n", $script:Utf8NoBom)
        Move-ItemWithRetry -Source $temporary -Destination $Path -Force
    } finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
    }
}

function Get-ManagedWindowsHook {
    param([string]$Client, [string]$HookPath)
    $escaped = '"' + $HookPath.Replace('"', '\"') + '"'
    if ($Client -eq 'claude') {
        return [pscustomobject][ordered]@{
            type = 'command'; command = 'powershell.exe'
            args = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $HookPath); timeout = 5
        }
    }
    $command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File $escaped"
    return [pscustomobject][ordered]@{
        type = 'command'; command = $command; commandWindows = $command; timeout = 5
    }
}

function Test-HookMatches {
    param($Hook, [string]$Client, [string]$HookPath)
    if ($null -eq $Hook) { return $false }
    $expected = Get-ManagedWindowsHook -Client $Client -HookPath $HookPath
    $actualProperties = @($Hook.PSObject.Properties | ForEach-Object { $_.Name } | Sort-Object) -join ','
    $expectedProperties = @($expected.PSObject.Properties | ForEach-Object { $_.Name } | Sort-Object) -join ','
    if ($actualProperties -ne $expectedProperties -or $Hook.type -ne $expected.type -or $Hook.timeout -ne $expected.timeout) {
        return $false
    }
    if ($Client -eq 'claude') {
        if (-not ([string]$Hook.command).Equals([string]$expected.command, [StringComparison]::OrdinalIgnoreCase)) { return $false }
        $actualArgs = @($Hook.args)
        $expectedArgs = @($expected.args)
        if ($actualArgs.Count -ne $expectedArgs.Count) { return $false }
        for ($index = 0; $index -lt $expectedArgs.Count; $index++) {
            if (-not ([string]$actualArgs[$index]).Equals([string]$expectedArgs[$index], [StringComparison]::OrdinalIgnoreCase)) { return $false }
        }
        return $true
    }
    return ([string]$Hook.command).Equals([string]$expected.command, [StringComparison]::OrdinalIgnoreCase) -and
        ([string]$Hook.commandWindows).Equals([string]$expected.commandWindows, [StringComparison]::OrdinalIgnoreCase)
}

function Update-HookJson {
    param([string]$Path, [string]$Client, [string]$HookPath, [ValidateSet('install', 'remove')][string]$Action)
    $data = Read-JsonObject -Path $Path
    if ($null -eq $data.PSObject.Properties['hooks']) { Set-ObjectProperty $data 'hooks' ([pscustomobject]@{}) }
    if ($null -eq $data.hooks -or $data.hooks -is [string] -or $data.hooks -is [ValueType] -or $data.hooks -is [System.Array]) { throw "hooks must be an object: $Path" }
    if ($null -eq $data.hooks.PSObject.Properties['UserPromptSubmit']) {
        Set-ObjectProperty $data.hooks 'UserPromptSubmit' @()
    } elseif ($data.hooks.UserPromptSubmit -isnot [System.Array]) {
        throw "hooks.UserPromptSubmit must be an array: $Path"
    }
    $entries = @($data.hooks.UserPromptSubmit)
    $cleaned = New-Object System.Collections.Generic.List[object]
    foreach ($entry in $entries) {
        if ($null -eq $entry -or $null -eq $entry.PSObject.Properties['hooks']) { $cleaned.Add($entry); continue }
        $kept = @($entry.hooks | Where-Object { -not (Test-HookMatches $_ $Client $HookPath) })
        if ($kept.Count -eq @($entry.hooks).Count) { $cleaned.Add($entry) }
        elseif ($kept.Count -gt 0) {
            $entry.hooks = $kept
            $cleaned.Add($entry)
        }
    }
    if ($Action -eq 'install') {
        $cleaned.Add([pscustomobject][ordered]@{ hooks = @((Get-ManagedWindowsHook $Client $HookPath)) })
    }
    if ($cleaned.Count -gt 0) { $data.hooks.UserPromptSubmit = [object[]]$cleaned.ToArray() }
    else { $data.hooks.PSObject.Properties.Remove('UserPromptSubmit') }
    if (@($data.hooks.PSObject.Properties).Count -eq 0) { $data.PSObject.Properties.Remove('hooks') }
    Write-JsonObject -Path $Path -Data $data
}

function Test-CodexInlineHooks {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    foreach ($line in Get-TomlCodeLines -Path $Path) {
        $lineWithoutComment = $line.Text.Trim()
        if ($lineWithoutComment -match '^\s*\[\[?\s*hooks(?:\.([A-Za-z][A-Za-z0-9]*))?(?:\.|\s*\])') {
            if ([string]::IsNullOrEmpty($Matches[1]) -or $Matches[1] -ne 'state') { return $true }
        }
        if ($lineWithoutComment -match '^hooks(?:\.[A-Za-z][A-Za-z0-9]*)?\s*=\s*\{') { return $true }
    }
    return $false
}

function Remove-TomlComment {
    param([string]$Line)
    $inSingleQuote = $false
    $inDoubleQuote = $false
    $escaped = $false
    for ($index = 0; $index -lt $Line.Length; $index++) {
        $character = $Line[$index]
        if ($inDoubleQuote) {
            if ($escaped) { $escaped = $false; continue }
            if ($character -eq '\') { $escaped = $true; continue }
            if ($character -eq '"') { $inDoubleQuote = $false }
            continue
        }
        if ($inSingleQuote) {
            if ($character -eq "'") { $inSingleQuote = $false }
            continue
        }
        if ($character -eq '"') { $inDoubleQuote = $true; continue }
        if ($character -eq "'") { $inSingleQuote = $true; continue }
        if ($character -eq '#') { return $Line.Substring(0, $index) }
    }
    return $Line
}

function Find-TomlMultilineClosing {
    param([string]$Text, [string]$Delimiter, [int]$StartIndex)
    $searchFrom = $StartIndex
    while ($searchFrom -lt $Text.Length) {
        $candidate = $Text.IndexOf($Delimiter, $searchFrom, [StringComparison]::Ordinal)
        if ($candidate -lt 0) { return -1 }
        if ($Delimiter -ne '"""') { return $candidate }

        $backslashes = 0
        for ($cursor = $candidate - 1; $cursor -ge 0 -and $Text[$cursor] -eq '\'; $cursor--) {
            $backslashes++
        }
        if (($backslashes % 2) -eq 0) { return $candidate }
        $searchFrom = $candidate + 1
    }
    return -1
}

# TOML 기본/리터럴 문자열과 다중행 문자열 내부를 설정 코드로 해석하지 않는다.
# 반환 객체의 Index는 원본 줄 번호이므로 안전한 in-place 갱신에 사용할 수 있다.
function Get-TomlCodeLines {
    param([string]$Path)
    $multilineDelimiter = $null
    $singleTriple = [string][char]39 + [char]39 + [char]39
    $lines = @(Get-Content -LiteralPath $Path -Encoding UTF8)
    for ($lineIndex = 0; $lineIndex -lt $lines.Count; $lineIndex++) {
        $raw = [string]$lines[$lineIndex]
        $builder = New-Object Text.StringBuilder
        $position = 0

        if ($null -ne $multilineDelimiter) {
            $closing = Find-TomlMultilineClosing -Text $raw -Delimiter $multilineDelimiter -StartIndex 0
            if ($closing -lt 0) {
                [pscustomobject]@{ Index = $lineIndex; Text = '' }
                continue
            }
            $position = $closing + 3
            $multilineDelimiter = $null
        }

        $inSingleQuote = $false
        $inDoubleQuote = $false
        $escaped = $false
        while ($position -lt $raw.Length) {
            $remaining = $raw.Length - $position
            $character = $raw[$position]

            if ($inDoubleQuote) {
                [void]$builder.Append($character)
                if ($escaped) { $escaped = $false }
                elseif ($character -eq '\') { $escaped = $true }
                elseif ($character -eq '"') { $inDoubleQuote = $false }
                $position++
                continue
            }
            if ($inSingleQuote) {
                [void]$builder.Append($character)
                if ($character -eq "'") { $inSingleQuote = $false }
                $position++
                continue
            }

            $delimiter = $null
            if ($remaining -ge 3) {
                $candidate = $raw.Substring($position, 3)
                if ($candidate -eq '"""' -or $candidate -eq $singleTriple) { $delimiter = $candidate }
            }
            if ($null -ne $delimiter) {
                $closing = Find-TomlMultilineClosing -Text $raw -Delimiter $delimiter -StartIndex ($position + 3)
                if ($closing -lt 0) {
                    $multilineDelimiter = $delimiter
                    break
                }
                $position = $closing + 3
                continue
            }
            if ($character -eq '#') { break }
            if ($character -eq '"') { $inDoubleQuote = $true }
            elseif ($character -eq "'") { $inSingleQuote = $true }
            [void]$builder.Append($character)
            $position++
        }
        [pscustomobject]@{ Index = $lineIndex; Text = $builder.ToString() }
    }
}

function Get-CodexHookFeatureState {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return [pscustomobject]@{ Value = $null; Key = $null; Dotted = $false; Inline = $false; Index = -1 } }
    $section = ''
    $found = @()
    foreach ($codeLine in Get-TomlCodeLines -Path $Path) {
        $index = $codeLine.Index
        $lineWithoutComment = $codeLine.Text.Trim()
        if ($lineWithoutComment -match '^\[\s*([^]]+)\s*\]$') { $section = $Matches[1].Trim(); continue }
        if ($section -eq '' -and $lineWithoutComment -match '^features\s*=\s*\{(.*)\}\s*$') {
            $inlineBody = $Matches[1]
            if ($inlineBody -match '["'']|[\[\]{}]') {
                throw "Inline Codex features with quoted or nested values require manual review: $Path"
            }
            foreach ($inlineItem in ($inlineBody -split ',')) {
                if ($inlineItem -match '^\s*(hooks|codex_hooks)\s*=\s*(true|false)\s*$') {
                    $found += [pscustomobject]@{ Value = $Matches[2] -eq 'true'; Key = $Matches[1]; Dotted = $false; Inline = $true; Index = $index }
                } elseif ($inlineItem -match '^\s*(hooks|codex_hooks)\s*=') {
                    throw "Unsupported inline Codex hook feature value: $Path"
                }
            }
            continue
        }
        if ($lineWithoutComment -match '^(?:(features)\.)?(hooks|codex_hooks)\s*=\s*(true|false)\s*$') {
            $dotted = -not [string]::IsNullOrEmpty($Matches[1])
            if (($section -eq 'features' -and -not $dotted) -or ($section -eq '' -and $dotted)) {
                $found += [pscustomobject]@{ Value = $Matches[3] -eq 'true'; Key = $Matches[2]; Dotted = $dotted; Inline = $false; Index = $index }
            }
        }
    }
    $canonical = @($found | Where-Object { $_.Key -eq 'hooks' } | Select-Object -First 1)
    if ($canonical.Count -gt 0) { return $canonical[0] }
    $deprecated = @($found | Select-Object -First 1)
    if ($deprecated.Count -gt 0) { return $deprecated[0] }
    return [pscustomobject]@{ Value = $null; Key = $null; Dotted = $false; Inline = $false; Index = -1 }
}

function Set-CodexHookFeatureValue {
    param([string]$Path, [bool]$Value, [string]$PreferredKey = 'hooks')
    $parent = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    $lines = @()
    if (Test-Path -LiteralPath $Path) { $lines = @(Get-Content -LiteralPath $Path -Encoding UTF8) }
    $state = Get-CodexHookFeatureState -Path $Path
    $textValue = $Value.ToString().ToLowerInvariant()
    if ($state.Index -ge 0) {
        $line = $lines[$state.Index]
        if ($state.Inline) {
            $inlineKey = [regex]::Escape([string]$state.Key)
            $inlinePattern = '(\{|,)(\s*)' + $inlineKey + '(\s*=\s*)(?:true|false)(?=\s*(?:,|\}))'
            $inlineMatch = [regex]::Match($line, $inlinePattern, [Text.RegularExpressions.RegexOptions]::IgnoreCase)
            if (-not $inlineMatch.Success) { throw "Inline Codex hook feature could not be updated: $Path" }
            $inlineReplacement = $inlineMatch.Groups[1].Value + $inlineMatch.Groups[2].Value + $PreferredKey + $inlineMatch.Groups[3].Value + $textValue
            $lines[$state.Index] = $line.Substring(0, $inlineMatch.Index) + $inlineReplacement + $line.Substring($inlineMatch.Index + $inlineMatch.Length)
        } else {
            $key = $PreferredKey
            if ($state.Dotted) { $key = 'features.' + $key }
            $lines[$state.Index] = [regex]::Replace($line, '^\s*(?:features\.)?(?:hooks|codex_hooks)(\s*=\s*)(?:true|false)', "$key`$1$textValue")
        }
    } else {
        if ($lines.Count -gt 0 -and -not [string]::IsNullOrWhiteSpace($lines[$lines.Count - 1])) { $lines += '' }
        $lines += '[features]'
        $lines += "hooks = $textValue"
    }
    [IO.File]::WriteAllText($Path, ($lines -join "`r`n") + "`r`n", $script:Utf8NoBom)
}

function Get-FileSnapshot {
    param([string]$Path)
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    if ($null -ne $item) {
        $isLink = ($null -ne $item.PSObject.Properties['LinkType']) -and $item.LinkType -eq 'SymbolicLink'
        $target = if ($isLink) { [string](@($item.Target)[0]) } else { $null }
        $bytes = if (-not $isLink -and -not $item.PSIsContainer) { [IO.File]::ReadAllBytes($Path) } else { $null }
        return [pscustomobject]@{ Exists = $true; IsLink = $isLink; LinkTarget = $target; Bytes = $bytes }
    }
    return [pscustomobject]@{ Exists = $false; IsLink = $false; LinkTarget = $null; Bytes = $null }
}

function Restore-FileSnapshot {
    param([string]$Path, $Snapshot)
    if ($Snapshot.Exists) {
        $parent = Split-Path -Parent $Path
        if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
        $currentItem = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
        if ($null -ne $currentItem -and $Snapshot.IsLink) {
            $currentIsLink = ($null -ne $currentItem.PSObject.Properties['LinkType']) -and $currentItem.LinkType -eq 'SymbolicLink'
            if ($currentIsLink -and [string](@($currentItem.Target)[0]) -eq $Snapshot.LinkTarget) { return }
        } elseif ($null -ne $currentItem -and -not $Snapshot.IsLink -and -not $currentItem.PSIsContainer) {
            $currentBytes = [IO.File]::ReadAllBytes($Path)
            if ([Convert]::ToBase64String($currentBytes) -eq [Convert]::ToBase64String($Snapshot.Bytes)) { return }
        }
        if (Test-Path -LiteralPath $Path) { Remove-Item -LiteralPath $Path -Recurse -Force }
        if ($Snapshot.IsLink) { New-Item -ItemType SymbolicLink -Path $Path -Target $Snapshot.LinkTarget | Out-Null }
        else { [IO.File]::WriteAllBytes($Path, $Snapshot.Bytes) }
    } elseif (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Force
    }
}

function Restore-SnapshotsBestEffort {
    param([Parameter(Mandatory = $true)][array]$Items)
    foreach ($item in $Items) {
        try {
            Restore-FileSnapshot -Path $item.Path -Snapshot $item.Snapshot
        } catch {
            Write-Warning "Rollback could not restore $($item.Path): $($_.Exception.Message)"
        }
    }
}

function Install-WorkflowHook {
    param([Parameter(Mandatory = $true)]$Layout, [Parameter(Mandatory = $true)][ValidateSet('claude', 'codex')][string]$Client, [switch]$EnableCodexHooks)
    if ($Layout.Scope -ne 'global') { throw 'Windows project scope does not install hooks.' }
    $hookComponent = @(Get-SupportedComponents -Client $Client -Platform windows -Kind hook | Where-Object { $_.name -eq 'workflow-reminder' }) | Select-Object -First 1
    if ($null -eq $hookComponent) { throw "Workflow hook is not supported for $Client on Windows." }
    $hookSource = Resolve-ComponentSource -Component $hookComponent -Client $Client
    if ($Client -eq 'claude') { $hookDirectory = $Layout.ClaudeHooks; $settings = $Layout.ClaudeSettings }
    else { $hookDirectory = $Layout.CodexHooks; $settings = $Layout.CodexHooksFile }
    $hookTarget = Join-Path $hookDirectory 'claude-code-skills-workflow.ps1'
    $existingHook = Get-Item -LiteralPath $hookTarget -Force -ErrorAction SilentlyContinue
    if ($null -ne $existingHook) {
        $existingEntry = Get-ManifestEntry -Layout $Layout -Target $hookTarget
        if (-not (Test-ManagedTarget -Target $hookTarget -Entry $existingEntry)) {
            Write-Warning "Preserving unverified or modified hook file: $hookTarget"
            return $false
        }
    }
    $hookSnapshot = Get-FileSnapshot $hookTarget
    $settingsSnapshot = Get-FileSnapshot $settings
    $configSnapshot = Get-FileSnapshot $Layout.CodexConfig
    $manifestSnapshot = Get-FileSnapshot $Layout.Manifest
    try {
        if ($Client -eq 'codex') {
            $state = Get-CodexHookFeatureState $Layout.CodexConfig
            if ($state.Value -eq $false) {
                if (-not $EnableCodexHooks) { throw 'Codex hooks are disabled in config.toml.' }
                Set-CodexHookFeatureValue -Path $Layout.CodexConfig -Value $true
            }
        }
        Copy-WithRollback -Source $hookSource -Target $hookTarget
        Update-HookJson -Path $settings -Client $Client -HookPath $hookTarget -Action install
        Save-ManifestEntry -Layout $Layout -Client $Client -Kind hook -Component workflow-reminder -Target $hookTarget -Method copy -Source $hookSource -Hash (Get-ContentHash $hookTarget) | Out-Null
        if ($Client -eq 'codex' -and $state.Value -eq $false) {
            Save-ManifestEntry -Layout $Layout -Client codex -Kind config -Component codex-hooks-feature -Target $Layout.CodexConfig -Method merge -Source $Layout.CodexConfig -Hash (Get-ContentHash $Layout.CodexConfig) -ConfigurationKey ([string]$state.Key) -ConfigurationBefore $false -ConfigurationAfter $true | Out-Null
        }
        Write-Host "[OK] $Client workflow hook -> $hookTarget" -ForegroundColor Green
        return $true
    } catch {
        $originalError = $_
        Restore-SnapshotsBestEffort @(
            [pscustomobject]@{ Path = $settings; Snapshot = $settingsSnapshot },
            [pscustomobject]@{ Path = $Layout.CodexConfig; Snapshot = $configSnapshot },
            [pscustomobject]@{ Path = $Layout.Manifest; Snapshot = $manifestSnapshot },
            [pscustomobject]@{ Path = $hookTarget; Snapshot = $hookSnapshot }
        )
        throw $originalError
    }
}

function Remove-WorkflowHook {
    param([Parameter(Mandatory = $true)]$Layout, [Parameter(Mandatory = $true)][ValidateSet('claude', 'codex')][string]$Client)
    if ($Client -eq 'claude') { $hookTarget = Join-Path $Layout.ClaudeHooks 'claude-code-skills-workflow.ps1'; $settings = $Layout.ClaudeSettings }
    else { $hookTarget = Join-Path $Layout.CodexHooks 'claude-code-skills-workflow.ps1'; $settings = $Layout.CodexHooksFile }
    $entry = Get-ManifestEntry -Layout $Layout -Target $hookTarget
    $configEntry = if ($Client -eq 'codex') { Get-ManifestEntry -Layout $Layout -Target $Layout.CodexConfig } else { $null }
    if ($null -eq $entry -and $null -eq $configEntry) {
        Write-Warning "No manifest ownership record; preserving hook settings and file: $hookTarget"
        return $false
    }
    if ($null -ne $entry -and (Test-Path -LiteralPath $hookTarget) -and -not (Test-ManagedTarget -Target $hookTarget -Entry $entry)) {
        Write-Warning "Hook file was modified; preserving hook settings and file: $hookTarget"
        return $false
    }
    $hookSnapshot = Get-FileSnapshot $hookTarget
    $settingsSnapshot = Get-FileSnapshot $settings
    $configSnapshot = Get-FileSnapshot $Layout.CodexConfig
    $manifestSnapshot = Get-FileSnapshot $Layout.Manifest
    try {
        if ($null -ne $entry) {
            if (Test-Path -LiteralPath $settings) { Update-HookJson -Path $settings -Client $Client -HookPath $hookTarget -Action remove }
            if (Test-Path -LiteralPath $hookTarget) { Remove-Item -LiteralPath $hookTarget -Force }
            Remove-ManifestEntry -Layout $Layout -Target $hookTarget
        }
        if ($Client -eq 'codex') {
        if ($null -ne $configEntry -and $configEntry.component -eq 'codex-hooks-feature' -and
            $null -ne $configEntry.configuration -and $configEntry.configuration.before -eq $false -and
            $configEntry.configuration.after -eq $true) {
            $current = Get-CodexHookFeatureState $Layout.CodexConfig
            if ($current.Value -eq $true) {
                Set-CodexHookFeatureValue -Path $Layout.CodexConfig -Value $false -PreferredKey ([string]$configEntry.configuration.key)
            } else {
                Write-Warning 'Codex hook feature changed after install; preserving the current value.'
            }
            Remove-ManifestEntry -Layout $Layout -Target $Layout.CodexConfig
        }
        }
        return $true
    } catch {
        $originalError = $_
        Restore-SnapshotsBestEffort @(
            [pscustomobject]@{ Path = $settings; Snapshot = $settingsSnapshot },
            [pscustomobject]@{ Path = $Layout.CodexConfig; Snapshot = $configSnapshot },
            [pscustomobject]@{ Path = $Layout.Manifest; Snapshot = $manifestSnapshot },
            [pscustomobject]@{ Path = $hookTarget; Snapshot = $hookSnapshot }
        )
        throw $originalError
    }
}

function Show-DependencyDiagnostics {
    $checks = @(
        @('Node.js', 'node', 'https://nodejs.org/'),
        @('PHP', 'php', 'winget install PHP.PHP'),
        @('Codex CLI', 'codex', 'npm install -g @openai/codex'),
        @('Context7 CLI', 'ctx7', 'npm install -g ctx7'),
        @('agent-browser', 'agent-browser', 'npm install -g agent-browser')
    )
    Write-Host "`nDependency diagnostics (nothing is installed automatically):" -ForegroundColor Cyan
    foreach ($check in $checks) {
        if ($null -ne (Get-Command $check[1] -ErrorAction SilentlyContinue)) { Write-Host "  [FOUND] $($check[0])" -ForegroundColor Green }
        else { Write-Host "  [MISSING] $($check[0]) - $($check[2])" -ForegroundColor Yellow }
    }
    $chromeCandidates = @()
    foreach ($base in @(${env:ProgramFiles}, ${env:ProgramFiles(x86)}, $env:LOCALAPPDATA)) {
        if (-not [string]::IsNullOrWhiteSpace($base)) {
            $chromeCandidates += Join-Path $base 'Google\Chrome\Application\chrome.exe'
        }
    }
    if (@($chromeCandidates | Where-Object { Test-Path -LiteralPath $_ }).Count -gt 0) { Write-Host '  [FOUND] Google Chrome' -ForegroundColor Green }
    else { Write-Host '  [MISSING] Google Chrome - https://www.google.com/chrome/' -ForegroundColor Yellow }
}

Export-ModuleMember -Function Get-RepositoryRoot, Get-ComponentCatalog, Get-SupportedComponents, Get-InstallLayout, Test-SymbolicLinkEligible, Install-ManagedComponent, Remove-ManagedComponent, Invoke-LegacyCodexSkillMigration, Test-CodexInlineHooks, Get-CodexHookFeatureState, Install-WorkflowHook, Remove-WorkflowHook, Show-DependencyDiagnostics
