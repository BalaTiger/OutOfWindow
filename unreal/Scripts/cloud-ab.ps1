param(
    [string]$EngineRoot = 'D:/UE_5.7',
    [string[]]$Cases = @('baseline','exposure-minus1','exposure-minus2','no-fog','no-bloom'),
    [string]$OutputName = 'settled',
    [int]$ResX = 1280,
    [int]$ResY = 820,
    [string]$Weather = 'moderate_rain',
    [float]$Hour = 12,
    [int]$Frames = 1,
    [float]$FrameInterval = 1,
    [switch]$AnimateClouds,
    [switch]$LiveTiming,
    [switch]$GpuProfile,
    [switch]$NoRainGlass,
    [float]$FixedExposureEV = [float]::NaN,
    [int]$CaptureSeconds = 20
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$output = Join-Path $repoRoot ".runtime/ue-cloud-ab/$OutputName"
New-Item -ItemType Directory -Path $output -Force | Out-Null
[Environment]::SetEnvironmentVariable('UE-LocalDataCachePath', 'D:/OutOfWindowBuildCache', 'Process')
$commands = @{
    'baseline' = ''
    'baseline-before' = 'oow.OvercastExposureBias -0.5'
    'exposure-minus1' = 'r.ExposureOffset -1'
    'exposure-minus2' = 'r.ExposureOffset -2'
    'no-fog' = 'r.Fog 0'
    'no-bloom' = 'r.BloomQuality 0'
    'layout8' = 'oow.CloudLayoutScale 8'
    'layout12' = 'oow.CloudLayoutScale 12'
    'no-cloud' = 'ShowFlag.Cloud 0'
    'cells' = ''
    'cells-legacy' = ''
    'cells-zero' = 'oow.StormDetailStrength 0'
    'cells-coarse' = 'oow.StormDetailScaleKm 0.55'
    'cells-fine' = 'oow.StormDetailScaleKm 0.18'
    'cells-partial' = 'oow.StormDetailStrength 0.75'
    'cells-thick' = 'oow.StormDetailDensityScale 1.35'
    'cells-thin' = 'oow.StormDetailDensityScale 0.9'
    'cells-dense' = 'oow.StormDetailDensityScale 2'
    'cells-scatter' = 'oow.StormScatterOcclusion 0.4'
    'cells-shadow' = 'oow.StormShadowSampleScale 1,oow.StormShadowDistanceKm 5'
    'cells-legacy-shadow' = 'oow.StormShadowSampleScale 1,oow.StormShadowDistanceKm 5'
    'cells-exposure-minus1' = 'r.ExposureOffset -1'
    'cells-exposure-minus2' = 'r.ExposureOffset -2'
    'cells-offsetx1' = 'oow.StormOffsetXKm 1'
    'cells-offsety1' = 'oow.StormOffsetYKm 1'
    'cells-spacing6' = 'oow.StormCellSpacingKm 6'
}
foreach ($case in $Cases) {
    if (!$commands.ContainsKey($case)) { throw "Unknown cloud A/B case: $case" }
    $arguments = @("$repoRoot/unreal/OutOfWindow/OutOfWindow.uproject", '/Game/Maps/Alley',
        '-game', '-RenderOffscreen', '-windowed', '-ForceRes', "-ResX=$ResX", "-ResY=$ResY",
        '-NoSplash', '-nosound', '-unattended', '-OOWTestScene=alley', "-OOWTestHour=$Hour",
        "-OOWTestWeather=$Weather", '-OOWTestQuality=1', "-OOWTestSeconds=$CaptureSeconds",
        '-OOWTestSettleWeather', "-OOWCaptureFrames=$Frames", "-OOWCaptureInterval=$FrameInterval",
        "-OOWCapture=$output/$case.png", "-AbsLog=$output/$case.log", '-stdout', '-FullStdOutLogOutput')
    if (!$LiveTiming) { $arguments += @('-UseFixedTimeStep','-FPS=10') }
    if (!$AnimateClouds) { $arguments += '-OOWTestFreezeClouds' }
    if ($NoRainGlass) { $arguments += '-OOWTestNoRainGlass' }
    if (![float]::IsNaN($FixedExposureEV)) { $arguments += "-OOWTestFixedExposureEV=$FixedExposureEV" }
    $execCommands = $commands[$case]
    if ($GpuProfile) {
        $profileCommands = "csvprofile STARTFILE=cloud-ab-$OutputName-$case.csv,csvprofile FRAMES=600"
        $execCommands = if ($execCommands) { "$execCommands,$profileCommands" } else { $profileCommands }
        $arguments += '-csvGpuStats'
    }
    if ($execCommands) { $arguments += "-ExecCmds=$execCommands" }
    if ($case.StartsWith('cells')) { $arguments += '-OOWTestStormCells' }
    else { $arguments += '-OOWTestNativeClouds' }
    if ($case.StartsWith('cells-legacy')) { $arguments += '-OOWTestLegacyStormCells' }
    $startedUtc = [DateTime]::UtcNow
    & "$EngineRoot/Engine/Binaries/Win64/UnrealEditor-Cmd.exe" @arguments *> "$output/$case-stdout.log"
    if ($LASTEXITCODE -ne 0) { throw "$case failed: $LASTEXITCODE" }
    if (Select-String -LiteralPath "$output/$case.log" -Pattern 'Failed to compile Material|Default Material will be used|Fatal error:|Ensure condition failed|screenshot timeout|OOW storm cloud material missing' -Quiet) { throw "$case failed rendering validation; see $output/$case.log" }
    foreach ($extension in @('png','json')) {
        $file = Get-Item -LiteralPath "$output/$case.$extension" -ErrorAction SilentlyContinue
        if (!$file -or $file.LastWriteTimeUtc -lt $startedUtc) { throw "$case has no fresh $extension" }
    }
    $state = Get-Content -LiteralPath "$output/$case.json" -Raw | ConvertFrom-Json
    if (!$state.captureSaved -or $state.capturedFrames -ne $Frames) { throw "$case did not complete capture" }
    $expectedMaterial = if ($case.StartsWith('cells-legacy')) { '/Game/Weather/MI_OOW_StormCells_v2.MI_OOW_StormCells_v2' } elseif ($case.StartsWith('cells')) { '/Game/Weather/MI_OOW_StormCells_v3.MI_OOW_StormCells_v3' } else { '/Engine/EngineSky/VolumetricClouds/m_SimpleVolumetricCloud_Inst.m_SimpleVolumetricCloud_Inst' }
    if ($state.cloudMaterial -ne $expectedMaterial) { throw "$case used unexpected cloud material: $($state.cloudMaterial)" }
    Write-Output "$case captured"
}
