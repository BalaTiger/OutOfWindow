param(
    [ValidateSet('Editor','Game','Build','Package','Import','Validate')][string]$Mode = 'Game',
    [string]$EngineRoot = $env:UE_ROOT,
    [ValidateSet('Alley','City','Village','Forest','Coast')][string]$Scene = 'Alley'
)
$ErrorActionPreference = 'Stop'
$projectRoot = Join-Path $PSScriptRoot 'OutOfWindow'
$projectFile = Join-Path $projectRoot 'OutOfWindow.uproject'
if (-not $EngineRoot) {
    $installed = Get-Content -LiteralPath 'C:\ProgramData\Epic\UnrealEngineLauncher\LauncherInstalled.dat' -Raw | ConvertFrom-Json
    $EngineRoot = ($installed.InstallationList | Where-Object AppName -eq 'UE_5.7' | Select-Object -First 1).InstallLocation
}
if (-not (Test-Path -LiteralPath (Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealEditor.exe'))) {
    throw 'UE 5.7 not found. Set UE_ROOT or pass -EngineRoot.'
}
$editor = Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealEditor.exe'
$commandlet = Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealEditor-Cmd.exe'
$build = Join-Path $EngineRoot 'Engine\Build\BatchFiles\Build.bat'
$uat = Join-Path $EngineRoot 'Engine\Build\BatchFiles\RunUAT.bat'
$cacheRoot = Join-Path ([System.IO.Path]::GetPathRoot($EngineRoot)) 'OutOfWindowBuildCache'
$buildRoot = Join-Path ([System.IO.Path]::GetPathRoot($EngineRoot)) 'OutOfWindowBuild'
New-Item -ItemType Directory -Path $cacheRoot -Force | Out-Null
[Environment]::SetEnvironmentVariable('UE-LocalDataCachePath', $cacheRoot, 'Process')
switch ($Mode) {
    'Build' {
        & $build OutOfWindowEditor Win64 Development "-Project=$projectFile" -WaitMutex -NoHotReloadFromIDE -NoUBA -MaxParallelActions=1
        if ($LASTEXITCODE) { exit $LASTEXITCODE }
        & $build OutOfWindow Win64 Development "-Project=$projectFile" -WaitMutex -NoHotReloadFromIDE -NoUBA -MaxParallelActions=1
        exit $LASTEXITCODE
    }
    'Editor' { & $editor $projectFile "/Game/Maps/$Scene" -NoSplash; exit $LASTEXITCODE }
    'Game' {
        $packaged = Join-Path $buildRoot 'Windows\OutOfWindow.exe'
        if (Test-Path -LiteralPath $packaged) { & $packaged "/Game/Maps/$Scene" -windowed -ResX=1280 -ResY=820 }
        else { & $editor $projectFile "/Game/Maps/$Scene" -game -windowed -ResX=1280 -ResY=820 -NoSplash }
        exit $LASTEXITCODE
    }
    'Import' {
        foreach ($script in @('import_scenes.py','build_window_interiors.py','build_surface_materials.py','build_precipitation.py','build_foam.py','build_coast_shoreline.py')) {
            & $commandlet $projectFile -run=pythonscript "-script=$(Join-Path $PSScriptRoot "Scripts\$script")" -unattended -nop4 -nosplash -NullRHI
            if ($LASTEXITCODE) { exit $LASTEXITCODE }
        }
    }
    'Package' {
        & $uat BuildCookRun "-project=$projectFile" -noP4 -platform=Win64 -clientconfig=Development -build -cook '-map=/Game/Maps/Alley+/Game/Maps/City+/Game/Maps/Village+/Game/Maps/Forest+/Game/Maps/Coast' -skipeditorcontent -stage -pak -iostore -archive '-ubtargs=-MaxParallelActions=1 -NoUBA' "-CookOutputDir=$(Join-Path $cacheRoot 'Cooked\Windows')" "-stagingdirectory=$(Join-Path $cacheRoot 'Staged')" "-archivedirectory=$buildRoot" -unattended -utf8output
        if ($LASTEXITCODE) { exit $LASTEXITCODE }
        Copy-Item -LiteralPath (Join-Path (Split-Path $PSScriptRoot -Parent) 'THIRD_PARTY_ASSETS.md') -Destination (Join-Path $buildRoot 'Windows\THIRD_PARTY_ASSETS.md') -Force
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Migration\asset-inventory.md') -Destination (Join-Path $buildRoot 'Windows\ASSET_INVENTORY.md') -Force
        exit $LASTEXITCODE
    }
    'Validate' { & (Join-Path $PSScriptRoot 'Scripts\validate.ps1') -EngineRoot $EngineRoot; exit $LASTEXITCODE }
}
