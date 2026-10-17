param([string]$LaunchScript)
$ErrorActionPreference = 'Stop'
if (-not $LaunchScript) {
    $LaunchScript = Join-Path $PSScriptRoot '..\..\Launch-Unreal.ps1'
    if (-not (Test-Path -LiteralPath $LaunchScript)) { $LaunchScript = Join-Path $PSScriptRoot '..\scripts\Launch-Unreal.ps1' }
}
$LaunchScript = (Resolve-Path -LiteralPath $LaunchScript).Path
$fixture = Join-Path $PSScriptRoot ('state-directory-selfcheck-' + [Guid]::NewGuid().ToString('N'))
$sources = Join-Path $fixture 'unreal\Launcher sources'
$customState = Join-Path $fixture '.runtime\candidate state with spaces'
$defaultState = Join-Path $fixture '.runtime\launcher'
$trailingState = (Join-Path $fixture '.runtime\candidate trailing slash') + '\'
New-Item -ItemType Directory -Path $sources -Force | Out-Null
$source = @'
using System;
using System.IO;
using System.Web.Script.Serialization;
class Program {
    [STAThread] static void Main(string[] args) {
        string root = null;
        foreach (string arg in args) if (arg.StartsWith("--root=")) root = arg.Substring(7);
        if (root == null) return;
        File.WriteAllText(Path.Combine(root, "arguments.json"), new JavaScriptSerializer().Serialize(args));
    }
}
'@
[IO.File]::WriteAllText((Join-Path $sources 'Program.cs'), $source)
$captures = @()
foreach ($state in @($customState, $defaultState, $trailingState)) {
    $argumentsPath = Join-Path $fixture 'arguments.json'
    if (Test-Path -LiteralPath $argumentsPath) { Remove-Item -LiteralPath $argumentsPath }
    $parameters = @{ RepositoryRoot = $fixture; LauncherSourceDirectory = $sources; Scene = 'City' }
    if ($state -ne $defaultState) { $parameters.OutputDirectory = $state }
    & $LaunchScript @parameters
    $deadline = [DateTime]::UtcNow.AddSeconds(10)
    while (-not (Test-Path -LiteralPath $argumentsPath) -and [DateTime]::UtcNow -lt $deadline) { Start-Sleep -Milliseconds 50 }
    if (-not (Test-Path -LiteralPath $argumentsPath)) { throw 'Argument-recording fixture did not execute.' }
    $received = @(Get-Content -LiteralPath $argumentsPath -Raw | ConvertFrom-Json)
    $normalizedState = [IO.Path]::GetFullPath($state).TrimEnd('\')
    if ($received -notcontains "--state-dir=$normalizedState") { throw "Launch script did not forward its normalized output directory: $normalizedState" }
    if ($received -notcontains "--root=$fixture" -or $received -notcontains '--scene=City') { throw 'Root/scene argument forwarding changed.' }
    $captures += [PSCustomObject]@{ outputDirectory = $state; normalizedOutputDirectory = $normalizedState; arguments = $received; passed = $true }
}
$result = [PSCustomObject]@{ passed = @('custom output state directory forwarded with spaces', 'default output state directory forwarded', 'trailing backslash normalized before command-line quoting', 'root and scene preserved'); captures = $captures; guiExecuted = $false; ueStarted = $false; fixture = $fixture }
$report = Join-Path $fixture 'results.json'
[IO.File]::WriteAllText($report, ($result | ConvertTo-Json -Depth 4), (New-Object Text.UTF8Encoding($false)))
Write-Output "STATE_DIRECTORY_SCRIPT_RESULTS=$report"
