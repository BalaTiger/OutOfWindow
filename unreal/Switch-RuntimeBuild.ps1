param(
    [Parameter(Mandatory=$true)][string]$Version,
    [string]$RepositoryRoot,
    [switch]$ValidateOnly
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if (-not $RepositoryRoot) { $RepositoryRoot = Split-Path -Parent $PSScriptRoot }
$RepositoryRoot = [IO.Path]::GetFullPath($RepositoryRoot).TrimEnd('\')
if (-not (Test-Path -LiteralPath (Join-Path $RepositoryRoot 'unreal\OutOfWindow\OutOfWindow.uproject') -PathType Leaf)) {
    throw "Not an OutOfWindow repository: $RepositoryRoot"
}
if ([String]::IsNullOrWhiteSpace($Version) -or $Version -in @('.', '..') -or
    $Version.IndexOfAny([IO.Path]::GetInvalidFileNameChars()) -ge 0 -or
    $Version -ne $Version.TrimEnd(' ', '.') -or [IO.Path]::IsPathRooted($Version)) {
    throw 'Version must be one directory name below .runtime\launcher-versions.'
}

function Get-RepositoryPath([string]$Path) {
    if ([String]::IsNullOrWhiteSpace($Path)) { throw 'An empty repository path was recorded.' }
    $full = [IO.Path]::GetFullPath([IO.Path]::Combine($RepositoryRoot, $Path))
    if (-not $full.StartsWith($RepositoryRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Path is outside this repository: $Path"
    }
    # Reject junctions as well as lexical traversal when checking repository containment.
    $check = $full
    while ($check -and $check -ne $RepositoryRoot) {
        if (Test-Path -LiteralPath $check) {
            if ((Get-Item -LiteralPath $check -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Repository paths must not pass through a junction or symlink: $check"
            }
        }
        $check = Split-Path -Parent $check
    }
    return $full
}

function Get-RequiredString($Object, [string]$Name) {
    $property = $Object.PSObject.Properties[$Name]
    if (-not $property -or $property.Value -isnot [string] -or [String]::IsNullOrWhiteSpace($property.Value)) {
        throw "Missing or invalid manifest field: $Name"
    }
    return $property.Value
}

function Assert-Hash([string]$Path, [string]$Expected) {
    if ($Expected -notmatch '^[0-9a-fA-F]{64}$') { throw "Invalid SHA256 for $Path" }
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Required file is missing: $Path" }
    if ((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash -ne $Expected) {
        throw "SHA256 mismatch: $Path"
    }
}

$versionsRoot = Get-RepositoryPath '.runtime\launcher-versions'
$versionDirectory = Get-RepositoryPath (Join-Path '.runtime\launcher-versions' $Version)
if ((Split-Path -Parent $versionDirectory) -ne $versionsRoot) { throw 'Version must name an immediate version directory.' }
$manifestPath = Get-RepositoryPath (Join-Path $versionDirectory 'target.json')
$proofPath = Get-RepositoryPath (Join-Path $versionDirectory 'runtime-content-proof.json')
$stateDirectory = Get-RepositoryPath '.runtime\launcher'
$activeManifest = Get-RepositoryPath (Join-Path $stateDirectory 'target.json')

$sha = [Security.Cryptography.SHA256]::Create()
try { $mutexKey = [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($RepositoryRoot.ToUpperInvariant()))).Replace('-', '').Substring(0, 24) }
finally { $sha.Dispose() }
$mutex = New-Object Threading.Mutex($false, ('Local\OutOfWindowRuntimeSwitch-' + $mutexKey))
$locked = $false
$temporaryManifest = $null
try {
    try { $locked = $mutex.WaitOne(15000) }
    catch [Threading.AbandonedMutexException] { $locked = $true }
    if (-not $locked) { throw 'Another runtime version switch is in progress.' }
    foreach ($file in @($manifestPath, $proofPath)) {
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Required version evidence is missing: $file" }
    }
    $manifestHash = (Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash
    $proofHash = (Get-FileHash -LiteralPath $proofPath -Algorithm SHA256).Hash
    $target = [IO.File]::ReadAllText($manifestPath) | ConvertFrom-Json
    $proof = [IO.File]::ReadAllText($proofPath) | ConvertFrom-Json
    if ($target -isnot [pscustomobject] -or $proof -isnot [pscustomobject]) { throw 'Version manifest and content proof must be JSON objects.' }
    $executable = Get-RequiredString $target 'executable'
    if ($executable -notmatch '^(?:[A-Za-z]:[\\/]|\\\\)' -or -not (Test-Path -LiteralPath $executable -PathType Leaf)) {
        throw "The recorded engine executable does not exist: $executable"
    }
    $projectPath = Get-RequiredString $target 'project'
    $modulePath = Get-RequiredString $target 'module'
    if ($projectPath -notmatch '^(?:[A-Za-z]:[\\/]|\\\\)' -or $modulePath -notmatch '^(?:[A-Za-z]:[\\/]|\\\\)') {
        throw 'Project and module paths must be absolute, as required by the launcher.'
    }
    $project = Get-RepositoryPath $projectPath
    if ([IO.Path]::GetExtension($project) -ne '.uproject' -or -not (Test-Path -LiteralPath $project -PathType Leaf)) {
        throw "The recorded project does not exist: $project"
    }
    $module = Get-RepositoryPath $modulePath
    $expectedModule = Join-Path (Split-Path -Parent $project) 'Binaries\Win64\UnrealEditor-OutOfWindow.dll'
    if ($module -ne $expectedModule) { throw 'The recorded module must belong to the selected project.' }
    Assert-Hash $module (Get-RequiredString $target 'moduleSha256')
    if (-not $target.PSObject.Properties['sources'] -or $target.sources -isnot [Array] -or $target.sources.Count -eq 0) {
        throw 'The version manifest must record its complete source set.'
    }
    $recorded = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    foreach ($source in $target.sources) {
        if (-not $source) { throw 'Invalid source record.' }
        $path = Get-RepositoryPath (Get-RequiredString $source 'path')
        Assert-Hash $path (Get-RequiredString $source 'sha256')
        if (-not $recorded.Add($path)) { throw "Duplicate source record: $path" }
    }
    if (-not $recorded.Contains($project)) { throw 'The selected project must be included in the source records.' }
    # As in Program.LoadTarget, each recorded project defines its own Source/Config roots.
    # A frozen rollback may intentionally record only its historical candidate project.
    foreach ($path in $recorded) {
        if ([IO.Path]::GetExtension($path) -ne '.uproject') { continue }
        foreach ($folder in @('Source', 'Config')) {
            $directory = Get-RepositoryPath (Join-Path (Split-Path -Parent $path) $folder)
            if (-not (Test-Path -LiteralPath $directory -PathType Container)) { continue }
            foreach ($file in Get-ChildItem -LiteralPath $directory -Recurse -File -Force) {
                $full = Get-RepositoryPath $file.FullName
                if (-not $recorded.Contains($full)) { throw "Unrecorded source/config file: $full" }
            }
        }
    }
    if (-not $proof.PSObject.Properties['files'] -or $proof.files -isnot [Array] -or $proof.files.Count -eq 0) {
        throw 'runtime-content-proof.json must contain a nonempty files array.'
    }
    $contentFiles = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    $projectContent = (Join-Path (Split-Path -Parent $project) 'Content') + '\'
    $hasProjectAsset = $false
    foreach ($file in $proof.files) {
        if (-not $file) { throw 'Invalid content proof record.' }
        $path = Get-RepositoryPath (Get-RequiredString $file 'path')
        Assert-Hash $path (Get-RequiredString $file 'sha256')
        if (-not $contentFiles.Add($path)) { throw "Duplicate content proof record: $path" }
        if ($path.StartsWith($projectContent, [StringComparison]::OrdinalIgnoreCase) -and [IO.Path]::GetExtension($path) -eq '.uasset') {
            $hasProjectAsset = $true
        }
    }
    if (-not $hasProjectAsset) { throw 'Content proof must include a .uasset from the selected project Content directory.' }
    Assert-Hash $manifestPath $manifestHash
    Assert-Hash $proofPath $proofHash
    $result = [ordered]@{
        status = 'VALIDATED'; version = $Version; manifest = $manifestPath
        project = $project; module = $module; sourceRecords = $recorded.Count
        contentRecords = $contentFiles.Count; targetSha256 = $manifestHash
        activeManifest = $activeManifest; activeChanged = $false; backup = $null
    }
    if (-not $ValidateOnly) {
        New-Item -ItemType Directory -Path $stateDirectory -Force | Out-Null
        $id = [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss-fff') + '-' + [Guid]::NewGuid().ToString('N')
        $temporaryManifest = Get-RepositoryPath (Join-Path $stateDirectory ("target-$id.tmp"))
        [IO.File]::Copy($manifestPath, $temporaryManifest, $false)
        Assert-Hash $temporaryManifest $manifestHash
        if (Test-Path -LiteralPath $activeManifest) {
            if (-not (Test-Path -LiteralPath $activeManifest -PathType Leaf)) { throw 'The active manifest path is not a file.' }
            $backupDirectory = Get-RepositoryPath (Join-Path $stateDirectory 'backups')
            New-Item -ItemType Directory -Path $backupDirectory -Force | Out-Null
            $result.backup = Get-RepositoryPath (Join-Path $backupDirectory ("target-$id.json"))
            # File.Replace preserves the exact superseded target and swaps atomically on one volume.
            [IO.File]::Replace($temporaryManifest, $activeManifest, $result.backup)
        }
        else { [IO.File]::Move($temporaryManifest, $activeManifest) }
        $temporaryManifest = $null
        $result.status = 'ACTIVATED'; $result.activeChanged = $true
    }
    $result | ConvertTo-Json -Depth 4
}
finally {
    if ($temporaryManifest -and (Test-Path -LiteralPath $temporaryManifest -PathType Leaf)) {
        Remove-Item -LiteralPath $temporaryManifest -Force
    }
    if ($locked) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
