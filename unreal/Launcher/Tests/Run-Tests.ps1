param([string]$CorePath, [switch]$Layout)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if (-not $CorePath) {
    $CorePath = Join-Path $PSScriptRoot '..\LaunchSession.cs'
    if (-not (Test-Path -LiteralPath $CorePath)) {
        $CorePath = Join-Path $PSScriptRoot '..\launcher\LaunchSession.cs'
    }
}
$CorePath = (Resolve-Path -LiteralPath $CorePath).Path
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $compiler)) { throw 'The .NET Framework C# compiler is required.' }
$buildDirectory = Join-Path $PSScriptRoot 'Build'
New-Item -ItemType Directory -Path $buildDirectory -Force | Out-Null
& $compiler '/nologo' '/codepage:65001' '/target:exe' "/out:$buildDirectory\FakeRenderer.exe" (Join-Path $PSScriptRoot 'FakeRenderer.cs')
if ($LASTEXITCODE -ne 0) { throw 'FakeRenderer compilation failed.' }
& $compiler '/nologo' '/codepage:65001' '/target:exe' '/r:System.Web.Extensions.dll' "/out:$buildDirectory\LaunchSessionTests.exe" (Join-Path $PSScriptRoot 'LaunchSessionTests.cs') $CorePath
if ($LASTEXITCODE -ne 0) { throw 'LaunchSessionTests compilation failed.' }
& (Join-Path $buildDirectory 'LaunchSessionTests.exe')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$programPath = Join-Path (Split-Path -Parent $CorePath) 'Program.cs'
& $compiler '/nologo' '/codepage:65001' '/target:exe' '/main:LauncherTargetTests' '/r:System.Web.Extensions.dll' '/r:System.Drawing.dll' '/r:System.Windows.Forms.dll' "/out:$buildDirectory\LauncherTargetTests.exe" (Join-Path $PSScriptRoot 'LauncherTargetTests.cs') $CorePath $programPath
if ($LASTEXITCODE -ne 0) { throw 'LauncherTargetTests compilation failed.' }
& (Join-Path $buildDirectory 'LauncherTargetTests.exe')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& (Join-Path $PSScriptRoot 'state-directory-selfcheck.ps1')
if ($Layout) {
    & $compiler '/nologo' '/codepage:65001' '/target:exe' '/main:LauncherLayoutTests' '/r:System.Web.Extensions.dll' '/r:System.Drawing.dll' '/r:System.Windows.Forms.dll' "/out:$buildDirectory\LauncherLayoutTests.exe" (Join-Path $PSScriptRoot 'LauncherLayoutTests.cs') $CorePath $programPath
    if ($LASTEXITCODE -ne 0) { throw 'LauncherLayoutTests compilation failed.' }
    & (Join-Path $buildDirectory 'LauncherLayoutTests.exe')
    exit $LASTEXITCODE
}
exit 0
