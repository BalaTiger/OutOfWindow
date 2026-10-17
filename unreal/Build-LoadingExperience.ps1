param(
    [string]$RepositoryRoot,
    [string]$ProjectRoot,
    [string]$EngineRoot = $env:UE_ROOT,
    [string]$LauncherSourceDirectory,
    [string]$OutputDirectory,
    [switch]$CopyContent,
    [switch]$PrepareOnly
)
$ErrorActionPreference = 'Stop'

if (-not $RepositoryRoot) {
    $RepositoryRoot = $PSScriptRoot
    while ($RepositoryRoot -and -not (Test-Path -LiteralPath (Join-Path $RepositoryRoot 'unreal\OutOfWindow\OutOfWindow.uproject'))) {
        $RepositoryRoot = Split-Path -Parent $RepositoryRoot
    }
}
if (-not $RepositoryRoot) { throw 'Cannot find the OutOfWindow repository. Pass -RepositoryRoot.' }
$RepositoryRoot = [IO.Path]::GetFullPath($RepositoryRoot).TrimEnd('\')
$sourceProject = Join-Path $RepositoryRoot 'unreal\OutOfWindow'
$continueCandidate = -not [String]::IsNullOrWhiteSpace($ProjectRoot)
if (-not $ProjectRoot) {
    # A normal rebuild always snapshots the current source; existing candidates stay untouched.
    $buildId = [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N').Substring(0, 8)
    $ProjectRoot = Join-Path $RepositoryRoot ('.runtime\loading-builds\' + $buildId + '\OutOfWindow')
    $CopyContent = $true
}
if ($continueCandidate -and -not $OutputDirectory) {
    throw 'Continuing an explicit -ProjectRoot also requires an explicit -OutputDirectory.'
}
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $RepositoryRoot '.runtime\launcher' }
if (-not $LauncherSourceDirectory) { $LauncherSourceDirectory = Join-Path $RepositoryRoot 'unreal\Launcher' }
$ProjectRoot = [IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\')
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory).TrimEnd('\')
foreach ($path in @($ProjectRoot, $OutputDirectory)) {
    if (-not $path.StartsWith($RepositoryRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Build outputs must be inside this repository: $path"
    }
}
if ($ProjectRoot -eq $sourceProject) { throw 'Use an isolated -ProjectRoot for the candidate build; this script never builds over the working project.' }
$projectFile = Join-Path $ProjectRoot 'OutOfWindow.uproject'
if (-not (Test-Path -LiteralPath $projectFile)) {
    if ((Test-Path -LiteralPath $ProjectRoot) -and @(Get-ChildItem -LiteralPath $ProjectRoot -Force).Count -ne 0) {
        throw "The candidate folder already contains files but no project; it was left unchanged: $ProjectRoot"
    }
    New-Item -ItemType Directory -Path $ProjectRoot -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $sourceProject 'OutOfWindow.uproject') -Destination $projectFile
    foreach ($name in @('Source', 'Config')) {
        Copy-Item -LiteralPath (Join-Path $sourceProject $name) -Destination (Join-Path $ProjectRoot $name) -Recurse
    }
}
# An explicit existing -ProjectRoot continues that candidate without overwriting edits.
if ($CopyContent -and -not (Test-Path -LiteralPath (Join-Path $ProjectRoot 'Content'))) {
    # A real copy preserves the working assets even if an editor writes an asset.
    Copy-Item -LiteralPath (Join-Path $sourceProject 'Content') -Destination (Join-Path $ProjectRoot 'Content') -Recurse
}
if ($PrepareOnly) { Write-Output $ProjectRoot; return }

if (-not $EngineRoot) {
    $installed = Get-Content -LiteralPath 'C:\ProgramData\Epic\UnrealEngineLauncher\LauncherInstalled.dat' -Raw | ConvertFrom-Json
    $EngineRoot = ($installed.InstallationList | Where-Object AppName -eq 'UE_5.7' | Select-Object -First 1).InstallLocation
}
if (-not $EngineRoot) { throw 'UE 5.7 not found. Pass -EngineRoot or set UE_ROOT.' }
$editor = Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealEditor.exe'
$ubt = Join-Path $EngineRoot 'Engine\Binaries\DotNET\UnrealBuildTool\UnrealBuildTool.dll'
$dotnet = Join-Path $EngineRoot 'Engine\Binaries\ThirdParty\DotNet\8.0.412\win-x64\dotnet.exe'
foreach ($path in @($editor, $ubt, $dotnet)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Required UE 5.7 build tool is missing: $path" }
}

New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$buildLogs = Join-Path $ProjectRoot 'Saved\LoadingBuild'
$buildTemp = Join-Path $buildLogs 'Temp'
$buildLocal = Join-Path $buildLogs 'LocalAppData'
$buildRoaming = Join-Path $buildLogs 'AppData'
New-Item -ItemType Directory -Path $buildLogs, $buildTemp, $buildLocal, $buildRoaming -Force | Out-Null
$buildLog = Join-Path $buildLogs 'UnrealBuildTool.log'
$launcherBootstrap = Join-Path $PSScriptRoot 'Launch-Unreal.ps1'
if (-not (Test-Path -LiteralPath $launcherBootstrap)) { throw "Launcher build script is missing: $launcherBootstrap" }

function Get-SourceRecords([string]$Root) {
    $files = @((Get-Item -LiteralPath (Join-Path $Root 'OutOfWindow.uproject')))
    $files += @(Get-ChildItem -LiteralPath (Join-Path $Root 'Source'), (Join-Path $Root 'Config') -Recurse -File)
    return @($files | Sort-Object FullName | ForEach-Object {
        [ordered]@{ path = $_.FullName.Substring($RepositoryRoot.Length + 1).Replace('\', '/'); sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash }
    })
}
function Get-ProjectFingerprint($Records, [string]$Root) {
    $prefixLength = $Root.Substring($RepositoryRoot.Length + 1).Length + 1
    return (@($Records | ForEach-Object { $_.path.Substring($prefixLength) + ':' + $_.sha256 }) -join "`n")
}
$sourceRecords = Get-SourceRecords $ProjectRoot
$beforeSources = $sourceRecords | ConvertTo-Json -Depth 4 -Compress
$workingSources = @()
if (-not $continueCandidate) {
    $workingSources = Get-SourceRecords $sourceProject
    if ((Get-ProjectFingerprint $sourceRecords $ProjectRoot) -ne (Get-ProjectFingerprint $workingSources $sourceProject)) {
        throw 'Working source changed while copying the snapshot. No target manifest was published; build again after edits finish.'
    }
}
$environmentNames = @('TEMP','TMP','LOCALAPPDATA','APPDATA','DOTNET_CLI_HOME','DOTNET_SKIP_FIRST_TIME_EXPERIENCE','DOTNET_CLI_TELEMETRY_OPTOUT')
$savedEnvironment = @{}
foreach ($name in $environmentNames) { $savedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
try {
    [Environment]::SetEnvironmentVariable('TEMP', $buildTemp, 'Process')
    [Environment]::SetEnvironmentVariable('TMP', $buildTemp, 'Process')
    [Environment]::SetEnvironmentVariable('LOCALAPPDATA', $buildLocal, 'Process')
    [Environment]::SetEnvironmentVariable('APPDATA', $buildRoaming, 'Process')
    [Environment]::SetEnvironmentVariable('DOTNET_CLI_HOME', $buildTemp, 'Process')
    [Environment]::SetEnvironmentVariable('DOTNET_SKIP_FIRST_TIME_EXPERIENCE', '1', 'Process')
    [Environment]::SetEnvironmentVariable('DOTNET_CLI_TELEMETRY_OPTOUT', '1', 'Process')
    # UE uses Windows Known Folders for some caches; sandbox denial is reported, never bypassed.
    $buildArgs = @($ubt, 'OutOfWindowEditor', 'Win64', 'Development', "-Project=$projectFile", '-WaitMutex',
        '-NoHotReloadFromIDE', '-NoUBA', '-NoUBALocal', '-NoXGE', '-MaxParallelActions=1', '-NoEngineChanges', "-Log=$buildLog")
    & $dotnet @buildArgs
    if ($LASTEXITCODE -ne 0) { throw "UE build failed (exit $LASTEXITCODE). No files were applied. Log: $buildLog" }
    & $launcherBootstrap -RepositoryRoot $RepositoryRoot -LauncherSourceDirectory $LauncherSourceDirectory -OutputDirectory $OutputDirectory -BuildOnly
}
finally {
    foreach ($name in $environmentNames) { [Environment]::SetEnvironmentVariable($name, $savedEnvironment[$name], 'Process') }
}

$module = Join-Path $ProjectRoot 'Binaries\Win64\UnrealEditor-OutOfWindow.dll'
if (-not (Test-Path -LiteralPath $module)) { throw "The successful build did not produce the expected module: $module" }
if (((Get-SourceRecords $ProjectRoot) | ConvertTo-Json -Depth 4 -Compress) -ne $beforeSources) {
    throw 'Candidate sources changed during compilation; no target manifest was published. Build again after edits finish.'
}
if (-not $continueCandidate -and ((Get-SourceRecords $sourceProject) | ConvertTo-Json -Depth 4 -Compress) -ne ($workingSources | ConvertTo-Json -Depth 4 -Compress)) {
    throw 'Working source changed during compilation; no target manifest was published. Build again after edits finish.'
}
$manifest = [ordered]@{
    executable = $editor
    project = $projectFile
    module = $module
    moduleSha256 = (Get-FileHash -LiteralPath $module -Algorithm SHA256).Hash
    sources = @($sourceRecords) + @($workingSources)
    builtUtc = [DateTime]::UtcNow.ToString('o')
}
$manifestFile = Join-Path $OutputDirectory 'target.json'
$temporaryManifest = $manifestFile + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
[IO.File]::WriteAllText($temporaryManifest, ($manifest | ConvertTo-Json -Depth 5), (New-Object Text.UTF8Encoding($false)))
if (Test-Path -LiteralPath $manifestFile) { [IO.File]::Replace($temporaryManifest, $manifestFile, [NullString]::Value) }
else { [IO.File]::Move($temporaryManifest, $manifestFile) }
Write-Output "Candidate built. Module: $module"
Write-Output "Candidate project: $projectFile"
Write-Output "Manifest: $manifestFile"
Write-Output 'The manifest uses this exact snapshot. No working project binary or asset was overwritten; no renderer was started.'
