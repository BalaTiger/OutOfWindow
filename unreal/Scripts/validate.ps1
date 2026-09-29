param(
    [Parameter(Mandatory=$true)][string]$EngineRoot,
    [string]$Cases = 'alley-clear,alley-rain,alley-night,alley-rainnight,city-clear,city-rain,village-clear,forest-clear,coast-clear,alley-snow,alley-fog,alley-ui',
    [ValidateRange(5,300)][int]$CaptureSeconds = 30,
    [ValidateSet('oak','ivory','graphite')][string]$FrameStyle = 'graphite',
    [switch]$Packaged,
    [string]$PackagedRoot
)
$ErrorActionPreference = 'Stop'
$unrealRoot = Split-Path $PSScriptRoot -Parent
$repoRoot = Split-Path $unrealRoot -Parent
$output = Join-Path $repoRoot '.runtime\ue-validation'
New-Item -ItemType Directory -Path $output -Force | Out-Null
[Environment]::SetEnvironmentVariable('UE-LocalDataCachePath', (Join-Path ([IO.Path]::GetPathRoot($EngineRoot)) 'OutOfWindowBuildCache'), 'Process')
$editor = Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealEditor-Cmd.exe'
$project = Join-Path $unrealRoot 'OutOfWindow\OutOfWindow.uproject'
if (-not $PackagedRoot) { $PackagedRoot = Join-Path ([IO.Path]::GetPathRoot($EngineRoot)) 'OutOfWindowBuild\Windows' }
$weatherPresets = @{
    clear = @(0, '晴'); cloudy = @(2, '多云'); overcast = @(3, '阴'); fog = @(45, '雾')
    rain = @(63, '中雨'); light_rain = @(61, '小雨'); moderate_rain = @(63, '中雨'); heavy_rain = @(65, '大雨')
    snow = @(73, '中雪'); light_snow = @(71, '小雪'); moderate_snow = @(73, '中雪'); heavy_snow = @(75, '大雪')
}
$results = @()
foreach ($case in $Cases.Split(',')) {
    $scene, $variant = $case.Split('-')
    $map = $scene.Substring(0,1).ToUpperInvariant() + $scene.Substring(1)
    $weatherMode = if ($variant -in @('rainnight', 'rainglass', 'lightrain')) { 'rain' } elseif ($weatherPresets.ContainsKey($variant)) { $variant } else { 'clear' }
    $weather = if ($weatherMode -match '(^|_)(rain|snow)$') { $Matches[2] } else { $weatherMode }
    $expectedCode, $expectedLabel = $weatherPresets[$weatherMode]
    $expectedMode = if ($weatherMode -in @('rain', 'snow')) { "moderate_$weatherMode" } else { $weatherMode }
    if ($variant -eq 'lightrain') { $expectedCode = 61; $expectedLabel = '小雨'; $expectedMode = 'real' }
    $hour = if ($variant -eq 'afternoon') { 16.5 } elseif ($variant -in @('night','rainnight')) { 23 } else { 12 }
    $prefix = if ($Packaged) { 'packaged-' } else { '' }
    $png = Join-Path $output "$prefix$case.png"
    $log = Join-Path $output "$prefix$case.log"
    # The seeded layout first finds a safe overtaking gap after about one minute.
    $caseCaptureSeconds = if ($variant -eq 'traffic') { [math]::Max(61, $CaptureSeconds) } elseif ($variant -eq 'input') { [math]::Max(20, $CaptureSeconds) } else { $CaptureSeconds }
    $arguments = @("/Game/Maps/$map", '-game', '-RenderOffscreen', '-windowed', '-ForceRes', '-ResX=1280', '-ResY=820', '-NoSplash', '-nosound', '-unattended',
        "-OOWTestScene=$scene", "-OOWTestHour=$hour", "-OOWTestWeather=$weatherMode", "-OOWTestSeconds=$caseCaptureSeconds", "-OOWCapture=$png", '-stdout', '-FullStdOutLogOutput')
    if ($variant -in @('ui', 'qualitymenu', 'locationmenu', 'input')) { $arguments += '-OOWCaptureUI' }
    if ($variant -eq 'qualitymenu') { $arguments += '-OOWTestMenu=quality' }
    if ($variant -eq 'lightrain') { $arguments += '-OOWTestPrecipitation=0.1' }
    if ($variant -eq 'locationmenu') { $arguments += '-OOWTestMenu=location' }
    if ($variant -eq 'input') { $arguments += '-OOWTestDesktopInput' }
    if ($variant -eq 'cloudmotion') { $arguments += @('-OOWCaptureFrames=16', '-OOWCaptureInterval=2') }
    if ($variant -eq 'traffic') { $arguments += @('-OOWCaptureFrames=16', '-OOWCaptureInterval=0.25') }
    if ($variant -eq 'rainglass') { $arguments += @('-OOWCaptureFrames=8', '-OOWCaptureInterval=0.5') }
    $caseFrameStyle = if ($variant -in @('ivory', 'graphite')) { $variant } else { $FrameStyle }
    $arguments += "-OOWFrame=$caseFrameStyle"
    if ($variant -eq 'ivory') { $arguments += '-OOWCaptureUI' }
    if ($variant -in @('hiddenui', 'narrow', 'wide', 'rainglass')) { $arguments += @('-OOWCaptureUI', '-OOWTestHideUI') }
    if ($variant -in @('narrow', 'wide')) {
        $arguments = @($arguments | Where-Object { $_ -notmatch '^-Res[XY]=' })
        if ($variant -eq 'narrow') { $arguments += @('-ResX=720', '-ResY=960') }
        else { $arguments += @('-ResX=1920', '-ResY=1080') }
    }
    if ($variant -eq 'eco') { $arguments += '-OOWTestQuality=0' }
    if ($variant -eq 'fine') { $arguments += '-OOWTestQuality=2' }
    if ($variant -eq 'desktop') {
        $arguments = @($arguments | Where-Object { $_ -ne '-RenderOffscreen' })
        $arguments += @('-OOWTestDesktop','-OOWCaptureUI')
    }
    $startedAtUtc = [DateTime]::UtcNow
    if ($Packaged) {
        $arguments += "-AbsLog=$log"
        $quoted = $arguments | ForEach-Object { '"' + $_.Replace('"','\"') + '"' }
        $process = Start-Process -FilePath (Join-Path $PackagedRoot 'OutOfWindow.exe') -ArgumentList $quoted -WindowStyle Hidden -Wait -PassThru
        $exitCode = $process.ExitCode
    }
    else { & $editor $project @arguments *> $log; $exitCode = $LASTEXITCODE }
    if ($exitCode -ne 0) { throw "$case exited with $exitCode. See $log" }
    if (Select-String -LiteralPath $log -Pattern 'Default Material will be used in game|Failed to compile Material' -Quiet) { throw "$case has a material fallback. See $log" }
    if (Select-String -LiteralPath $log -Pattern 'Ensure condition failed|Fatal error:|OOW screenshot timeout' -Quiet) { throw "$case hit an engine runtime check. See $log" }
    if (Select-String -LiteralPath $log -Pattern 'Nanite DDC request failed|marking resource invalid' -Quiet) { throw "$case has missing Nanite geometry. Check concurrent editor DDC settings. See $log" }
    if ($variant -eq 'input' -and -not (Select-String -LiteralPath $log -Pattern 'OOW_DESKTOP_INPUT_TEST_PASS' -Quiet)) { throw "$case failed background UI input checks. See $log" }
    $statePath = [IO.Path]::ChangeExtension($png, 'json')
    if (-not (Test-Path $png) -or -not (Test-Path $statePath)) { throw "$case did not produce a capture and audit" }
    $state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
    $expectedFrames = if ($variant -in @('cloudmotion', 'traffic')) { 16 } elseif ($variant -eq 'rainglass') { 8 } else { 1 }
    if ($state.capturedFrames -ne $expectedFrames) { throw "$case did not finish all captures" }
    $captureFiles = @($png, $statePath)
    if ($expectedFrames -gt 1) {
        $captureFiles += 0..($expectedFrames - 2) | ForEach-Object { Join-Path $output ('{0}{1}-{2:D3}.png' -f $prefix, $case, $_) }
    }
    foreach ($captureFile in $captureFiles) {
        if (-not (Test-Path -LiteralPath $captureFile) -or (Get-Item -LiteralPath $captureFile).LastWriteTimeUtc -lt $startedAtUtc) { throw "$case has a missing or stale capture: $captureFile" }
    }
    if ($state.missingTags.Count -or -not $state.cameraBound -or -not $state.captureSaved) { throw "$case has incomplete scene state" }
    if (-not $state.desktopFrameReady -or $state.desktopFrameTriangles -le 0) { throw "$case lost its physical window frame" }
    if ($state.desktopRoomWalls -ne 9) { throw "$case lost its enclosing room" }
    if ($null -eq $state.desktopRoomLampLumens -or ($hour -ge 12 -and $hour -le 16.5 -and $state.desktopRoomLampLumens -ne 0) -or ($hour -eq 23 -and $state.desktopRoomLampLumens -le 0)) { throw "$case has incorrect indoor day/night lighting" }
    if ($variant -eq 'overcast' -and $state.cloudiness -lt .98) { throw "$case did not reach overcast cloud cover" }
    if ($state.desktopFrameStyle -ne $caseFrameStyle) { throw "$case did not apply the requested frame style" }
    if ($variant -in @('hiddenui', 'narrow', 'wide', 'rainglass') -and -not $state.interfaceHidden) { throw "$case did not hide the interface" }
    if ($null -eq $state.windowRainIntensity -or ($weather -eq 'rain' -and $state.windowRainIntensity -le 0) -or ($weather -ne 'rain' -and $state.windowRainIntensity -ne 0)) { throw "$case has incorrect rain on its foreground glass" }
    if ($state.'r.DynamicGlobalIlluminationMethod' -ne 1 -or $state.'r.ReflectionMethod' -ne 1) { throw "$case did not use Lumen" }
    if ($state.'r.Lumen.Reflections.Allow' -ne 1 -or $state.'r.Lumen.DiffuseIndirect.Allow' -ne 1) { throw "$case disabled Lumen passes" }
    if ($state.'r.Lumen.ScreenProbeGather.TwoSidedFoliageBackfaceDiffuse' -ne 1) { throw "$case lost two-sided backface GI for canvas and foliage" }
    if ($state.'r.VolumetricCloud' -ne 1 -or $state.'r.VolumetricRenderTarget' -ne 1 -or $state.cloudLayerBottomKm -le 0 -or $state.cloudLayerHeightKm -le 0) { throw "$case has inactive clouds" }
    if ($null -eq $state.visibleSkyFraction -or $state.visibleSkyFraction -lt 0 -or $state.visibleSkyFraction -gt 1 -or $null -eq $state.visibleSkyPixels -or $state.visibleSkyPixels -lt 0) { throw "$case lacks a valid rendered sky-area measurement" }
    if ($state.'r.VolumetricRenderTarget.Mode' -ne 0 -or $state.'r.VolumetricCloud.DistanceToSampleMaxCount' -ne 5) { throw "$case lost its stable cloud reconstruction settings" }
    $sampleFloor = .5 * ($state.quality + 1)
    $sampleCap = $state.quality + 1
    foreach ($sampleScale in @($state.cloudViewSampleScale, $state.cloudTargetSampleScale)) {
        if ($null -eq $sampleScale -or $sampleScale -lt $sampleFloor - .001 -or $sampleScale -gt $sampleCap + .001) { throw "$case cloud samples escaped its quality budget" }
    }
    if ($state.cloudParameters.Layout_CloudGlobalScale -ne 32 -or $state.cloudDriftUV.Count -ne 2 -or ([math]::Abs($state.cloudDriftUV[0]) + [math]::Abs($state.cloudDriftUV[1])) -le .00001) { throw "$case cloud layout is not drifting with weather wind" }
    if ($weather -in @('rain', 'snow') -and ($state.cloudParameters.StormClouds -lt .65 -or $state.atmosphereMieScale -lt 2 * $state.atmosphereBaseMieScale)) { throw "$case retained a clear-weather sky" }
    if ($weather -notin @('rain', 'snow') -and $state.cloudParameters.StormClouds -gt .01) { throw "$case applied storm clouds without precipitation" }
    if ($variant -eq 'cloudmotion' -and $state.capturedFrames -ne 16) { throw "$case lacks its 30-second cloud-motion sequence" }
    if ($state.staticMeshComponents -lt 6 -or $state.naniteMeshComponents -lt 1 -or $state.materialInstances -lt 1) { throw "$case has missing geometry or materials" }
    if ($scene -eq 'alley') {
        if ($state.windMeshComponents -le 0 -or $state.evaluatedWindMeshComponents -ne $state.windMeshComponents -or $state.windMaterialSlots -le 0 -or $state.windStrengthMetersPerSecond -le 0) { throw "$case has inactive wind geometry or materials" }
        if ($state.anchoredWindMeshComponents -ne $state.windMeshComponents) { throw "$case lacks saved wind attachment bounds" }
        if ($state.compiledWindMaterialSlots -ne $state.windMaterialSlots) { throw "$case compiled wind materials without vertex displacement" }
        if (-not $state.birdGeometryReady) { throw "$case could not build the bird geometry" }
        if (($hour -eq 23 -or $weather -notin @('clear', 'cloudy')) -and $state.activeBirds -ne 0) { throw "$case has birds in unsuitable weather or at night" }
        if ($state.windowGlassFronts -le 0 -or $state.windowGlassFronts -ne $state.windowGlassBackings) { throw "$case has incomplete front/back glass pairs" }
        if ($state.interiorLights -le 0 -or $state.interiorLights -gt 12) { throw "$case has an invalid window-light budget" }
        if ($hour -eq 12 -and $state.interiorLightLumens -gt .01) { throw "$case kept room lights on during daytime" }
        if ($hour -eq 23 -and $state.interiorLightLumens -le 0) { throw "$case has no night window illumination" }
        if ($null -eq $state.finalViewPostProcess) { throw "$case lacks final view exposure/bloom evidence" }
    }
    if ($weather -eq 'rain' -and $state.wetness -le 0) { throw "$case wetness did not respond" }
    if ($variant -eq 'lightrain' -and ([math]::Abs($state.windowRainIntensity - .32538149) -gt .00001 -or $state.water -le 0 -or $state.water -gt .489)) { throw "$case did not retain light-rain intensity and partial puddle coverage" }
    if ($scene -eq 'city') {
        if ($state.movingCars -ne 16 -or $state.traffic.Count -ne 16) { throw 'City traffic migration incomplete' }
        if ($state.nightLights -ne 18 -or $state.maxHeadlights -ne 8 -or $null -eq $state.activeHeadlights -or $state.activeHeadlights -gt 8) { throw 'City street/headlight budget incomplete' }
        if (($hour -eq 23 -and $state.activeHeadlights -le 0) -or ($hour -eq 12 -and $state.activeHeadlights -ne 0)) { throw 'City headlight day/night control failed' }
        if ($null -eq $state.trafficMinimumGapMeters -or $state.trafficMinimumGapMeters -lt 2.49) { throw 'City traffic lost its safe following gap' }
        foreach ($car in $state.traffic) {
            if ($car.speedKmh -lt 0 -or $car.speedKmh -gt 50.01 -or $car.desiredSpeedKmh -lt 34 -or $car.desiredSpeedKmh -gt 50) { throw 'City traffic speed outside its urban range' }
            if ([math]::Abs($car.x) -lt 219.9 -or [math]::Abs($car.x) -gt 520.1 -or ($car.x -gt 0) -ne ($car.id % 2 -eq 0)) { throw 'City traffic crossed its carriageway boundary' }
        }
        if ($variant -eq 'traffic' -and ($state.trafficLaneChanges -le 0 -or $state.trafficOvertakeChanges -le 0)) { throw 'City traffic did not demonstrate overtaking lane changes' }
    }
    if ($state.scene -ne $map -or $state.actualWeather -ne $weather -or [math]::Abs($state.hour - $hour) -gt .02) { throw "$case did not apply its requested state" }
    if ($state.weatherMode -ne $expectedMode -or $state.weatherCode -ne $expectedCode -or $state.weatherLabel -ne $expectedLabel) { throw "$case did not apply its precise weather label and code" }
    if ($variant -eq 'desktop') {
        $desktop = Get-Content -LiteralPath ([IO.Path]::ChangeExtension($png, 'desktop.json')) -Raw | ConvertFrom-Json
        if (-not $desktop.passed) { throw "$case failed native desktop checks" }
    }
    $results += $state
    Write-Output "$case passed; frame p95 $([math]::Round($state.frameTimeP95Ms,1)) ms; $($state.naniteMeshComponents) Nanite components"
}
$summaryName = if ($Packaged) { 'packaged-summary.json' } else { 'summary.json' }
$results | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $output $summaryName) -Encoding utf8
