# Okta sweep: capture the alley and let scripts/okta-v0.py measure the
# visible-sky okta for each case. Two axes, picked by which list is given:
#   -Codes       0,1,2,3   -> -OOWTestWeatherCode (label; amount follows
#                             DefaultCloudCoverForCode, so this axis moves both)
#   -CloudCovers 0,20,...,100 -> -OOWTestCloudCover (the CloudCover->okta transfer curve,
#                                 V1: no source change needed, CloudBlend sweeps coverage)
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/okta-v0-sweep.ps1 -CloudCovers 0,20,40,60,80,100 -Hours 12
# Lists: -File already comma-binds into an array, but a plain string still
# needs splitting (-split on an array would join it into one token).
param(
    [object]$Codes = '',
    [object]$Hours = '12',
    [object]$CloudCovers = '',
    [int]$Seconds = 14
)
function Expand-List($v) {
    @($v) | ForEach-Object { if ($_ -is [string]) { $_ -split ',' } else { $_ } } |
        Where-Object { "$_" -ne '' } | ForEach-Object { [int]$_ }
}
$Codes = Expand-List $Codes
$Hours = Expand-List $Hours
$CloudCovers = Expand-List $CloudCovers
if (-not $Codes) { $Codes = @(0, 1, 2, 3) }
$ErrorActionPreference = 'Stop'
$root   = Split-Path $PSScriptRoot -Parent
$out    = Join-Path $root '.runtime/okta-v0'
$editor = 'D:/Epic/Epic Games/UE_5.7/Engine/Binaries/Win64/UnrealEditor.exe'
$uproj  = Join-Path $root 'unreal/OutOfWindow/OutOfWindow.uproject'
New-Item -ItemType Directory -Force $out | Out-Null

# One case per render: a weather code, or (when -CloudCovers is given) a
# cloud-cover percent that sweeps the amount path directly.
$cases = if ($CloudCovers) { $CloudCovers | ForEach-Object { @{ Name = "cv$_"; Arg = "-OOWTestCloudCover=$_" } } }
         else { $Codes | ForEach-Object { @{ Name = "c$_"; Arg = "-OOWTestWeatherCode=$_" } } }
$json = @()
foreach ($h in $Hours) {
    foreach ($case in $cases) {
        $name = "$($case.Name)h${h}"
        $png  = "$out/$name.png"
        if (-not (Test-Path $png)) {
            Write-Host "== $name =="
            $args = @($uproj, '/Game/Maps/Alley', '-game', '-RenderOffscreen', '-windowed',
                '-ForceRes', '-ResX=1280', '-ResY=820', '-NoSplash', '-nosound', '-unattended',
                "-OOWTestScene=alley", "-OOWTestHour=$h", $case.Arg,
                '-OOWTestQuality=1', "-OOWTestSeconds=$Seconds",
                '-OOWTestSettleWeather', '-OOWTestFreezeClouds',
                "-OOWCapture=$png", "-AbsLog=$out/$name.log", '-stdout', '-FullStdOutLogOutput')
            $p = Start-Process -FilePath $editor -ArgumentList $args -WindowStyle Hidden -Wait -PassThru
            if ($p.ExitCode) { throw "Capture $name failed: $($p.ExitCode)" }
            if (-not (Test-Path $png)) { throw "Capture $name produced no image" }
        } else { Write-Host "skip $name" }
        $j = "$out/$name.json"
        if (Test-Path $j) { $json += $j }
    }
}
python "$PSScriptRoot/okta-v0.py" $json
