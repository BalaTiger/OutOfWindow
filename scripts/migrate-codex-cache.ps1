$ErrorActionPreference = 'Stop'

# Run this after closing Codex. It moves the active Codex home and runtime
# cache to E:, then leaves junctions at the old paths for compatibility.
$codexProcesses = Get-Process -Name codex,codex-server,codex-desktop -ErrorAction SilentlyContinue
if ($codexProcesses) {
  throw 'Codex is still running. Close the Codex desktop app and all Codex CLI processes, then run this script again.'
}

$targetRoot = 'E:\Codex'
$homeSource = 'C:\Users\zhuzi\.codex'
$homeTarget = Join-Path $targetRoot 'codex-home'
$runtimeSource = 'C:\Users\zhuzi\.cache\codex-runtimes'
$runtimeTarget = Join-Path $targetRoot 'cache\codex-runtimes'

New-Item -ItemType Directory -Force -Path $targetRoot | Out-Null

function Move-ToJunction([string]$source, [string]$target) {
  if (-not (Test-Path -LiteralPath $source)) { return }
  $sourceItem = Get-Item -LiteralPath $source -Force
  if ($sourceItem.Attributes -band [IO.FileAttributes]::ReparsePoint) { return }
  if (Test-Path -LiteralPath $target) {
    $existing = Get-ChildItem -LiteralPath $target -Force -ErrorAction SilentlyContinue
    if ($existing) { throw "Target is not empty: $target" }
  } else {
    New-Item -ItemType Directory -Force -Path $target | Out-Null
  }
  robocopy $source $target /E /MOVE /COPY:DAT /DCOPY:DAT /R:2 /W:1 /NFL /NDL /NJH /NJS | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "Robocopy failed for $source (exit code $LASTEXITCODE)." }
  if ((Get-ChildItem -LiteralPath $source -Force -ErrorAction SilentlyContinue | Measure-Object).Count -ne 0) {
    throw "Migration incomplete: $source"
  }
  Remove-Item -LiteralPath $source -Force
  New-Item -ItemType Junction -Path $source -Target $target | Out-Null
  Write-Output "Moved $source -> $target"
}

Move-ToJunction $homeSource $homeTarget
Move-ToJunction $runtimeSource $runtimeTarget

[Environment]::SetEnvironmentVariable('CODEX_HOME', $homeTarget, 'User')
[Environment]::SetEnvironmentVariable('XDG_CACHE_HOME', (Join-Path $targetRoot 'cache'), 'User')
Write-Output "CODEX_HOME=$homeTarget"
Write-Output "XDG_CACHE_HOME=$(Join-Path $targetRoot 'cache')"
Write-Output 'Restart Codex and any terminals so they inherit the new user environment.'
