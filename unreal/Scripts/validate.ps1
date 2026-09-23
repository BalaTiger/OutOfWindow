param(
    [Parameter(Mandatory=$true)][string]$EngineRoot,
    [string]$Cases = 'alley-clear,alley-rain,alley-night,alley-rainnight,city-clear,city-rain,village-clear,forest-clear,coast-clear,alley-snow,alley-fog,alley-ui',
    [ValidateRange(5,300)][int]$CaptureSeconds = 30,
    [switch]$Packaged
)
$ErrorActionPreference = 'Stop'
$unrealRoot = Split-Path $PSScriptRoot -Parent
$repoRoot = Split-Path $unrealRoot -Parent
$output = Join-Path $repoRoot '.runtime\ue-validation'
New-Item -ItemType Directory -Path $output -Force | Out-Null
[Environment]::SetEnvironmentVariable('UE-LocalDataCachePath', (Join-Path ([IO.Path]::GetPathRoot($EngineRoot)) 'OutOfWindowBuildCache'), 'Process')
$editor = Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealEditor-Cmd.exe'
$project = Join-Path $unrealRoot 'OutOfWindow\OutOfWindow.uproject'
$results = @()
foreach ($case in $Cases.Split(',')) {
    $scene, $variant = $case.Split('-')
    $map = $scene.Substring(0,1).ToUpperInvariant() + $scene.Substring(1)
    $weather = if ($variant -eq 'rainnight') { 'rain' } elseif ($variant -in @('rain','snow','fog')) { $variant } else { 'clear' }
    $hour = if ($variant -in @('night','rainnight')) { 23 } else { 12 }
    $prefix = if ($Packaged) { 'packaged-' } else { '' }
    $png = Join-Path $output "$prefix$case.png"
    $log = Join-Path $output "$prefix$case.log"
    $arguments = @("/Game/Maps/$map", '-game', '-RenderOffscreen', '-windowed', '-ForceRes', '-ResX=1280', '-ResY=820', '-NoSplash', '-nosound', '-unattended',
        "-OOWTestScene=$scene", "-OOWTestHour=$hour", "-OOWTestWeather=$weather", "-OOWTestSeconds=$CaptureSeconds", "-OOWCapture=$png", '-stdout', '-FullStdOutLogOutput')
    if ($variant -eq 'ui') { $arguments += '-OOWCaptureUI' }
    if ($variant -eq 'eco') { $arguments += '-OOWTestQuality=0' }
    if ($variant -eq 'fine') { $arguments += '-OOWTestQuality=2' }
    if ($variant -eq 'desktop') {
        $arguments = @($arguments | Where-Object { $_ -ne '-RenderOffscreen' })
        $arguments += @('-OOWTestDesktop','-OOWCaptureUI')
    }
    if ($Packaged) {
        $arguments += "-AbsLog=$log"
        $quoted = $arguments | ForEach-Object { '"' + $_.Replace('"','\"') + '"' }
        $process = Start-Process -FilePath (Join-Path ([IO.Path]::GetPathRoot($EngineRoot)) 'OutOfWindowBuild\Windows\OutOfWindow.exe') -ArgumentList $quoted -WindowStyle Hidden -Wait -PassThru
        $exitCode = $process.ExitCode
    }
    else { & $editor $project @arguments *> $log; $exitCode = $LASTEXITCODE }
    if ($exitCode -ne 0) { throw "$case exited with $exitCode. See $log" }
    if (Select-String -LiteralPath $log -Pattern 'Default Material will be used in game|Failed to compile Material' -Quiet) { throw "$case has a material fallback. See $log" }
    $statePath = [IO.Path]::ChangeExtension($png, 'json')
    if (-not (Test-Path $png) -or -not (Test-Path $statePath)) { throw "$case did not produce a capture and audit" }
    $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    if ($state.missingTags.Count -or -not $state.cameraBound -or -not $state.captureSaved) { throw "$case has incomplete scene state" }
    if ($state.'r.DynamicGlobalIlluminationMethod' -ne 1 -or $state.'r.ReflectionMethod' -ne 1) { throw "$case did not use Lumen" }
    if ($state.'r.Lumen.Reflections.Allow' -ne 1 -or $state.'r.Lumen.DiffuseIndirect.Allow' -ne 1) { throw "$case disabled Lumen passes" }
    if ($state.staticMeshComponents -lt 6 -or $state.naniteMeshComponents -lt 1 -or $state.materialInstances -lt 1) { throw "$case has missing geometry or materials" }
    if ($weather -eq 'rain' -and $state.wetness -le 0) { throw "$case wetness did not respond" }
    if ($scene -eq 'city' -and $state.movingCars -ne 16) { throw 'City traffic migration incomplete' }
    if ($state.scene -ne $map -or $state.actualWeather -ne $weather -or [math]::Abs($state.hour - $hour) -gt .02) { throw "$case did not apply its requested state" }
    if ($variant -eq 'desktop') {
        $desktop = Get-Content -LiteralPath ([IO.Path]::ChangeExtension($png, 'desktop.json')) -Raw | ConvertFrom-Json
        if (-not $desktop.passed) { throw "$case failed native desktop checks" }
    }
    $results += $state
    Write-Output "$case passed; frame p95 $([math]::Round($state.frameTimeP95Ms,1)) ms; $($state.naniteMeshComponents) Nanite components"
}
$summaryName = if ($Packaged) { 'packaged-summary.json' } else { 'summary.json' }
$results | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $output $summaryName) -Encoding utf8
