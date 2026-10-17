param(
    [string]$RepositoryRoot,
    [ValidateSet('Alley','City','Village','Forest','Coast')][string]$Scene = 'Alley',
    [string]$LauncherSourceDirectory,
    [string]$OutputDirectory,
    [switch]$BuildOnly
)
$ErrorActionPreference = 'Stop'

try {
    if (-not $RepositoryRoot) {
        $RepositoryRoot = $PSScriptRoot
        while ($RepositoryRoot -and -not (Test-Path -LiteralPath (Join-Path $RepositoryRoot 'unreal\OutOfWindow\OutOfWindow.uproject'))) {
            $RepositoryRoot = Split-Path -Parent $RepositoryRoot
        }
    }
    if (-not $RepositoryRoot) { throw 'Cannot find the OutOfWindow repository. Pass -RepositoryRoot.' }
    $RepositoryRoot = [IO.Path]::GetFullPath($RepositoryRoot).TrimEnd('\')
    if (-not $LauncherSourceDirectory) { $LauncherSourceDirectory = Join-Path $RepositoryRoot 'unreal\Launcher' }
    if (-not $OutputDirectory) { $OutputDirectory = Join-Path $RepositoryRoot '.runtime\launcher' }
    $OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory).TrimEnd('\')
    if (-not $OutputDirectory.StartsWith($RepositoryRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Launcher output must be inside this repository.'
    }
    New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
    $launcher = Join-Path $OutputDirectory 'OutOfWindow.Launcher.exe'
    $stampFile = Join-Path $OutputDirectory 'launcher-build.json'
    $buildLog = Join-Path $OutputDirectory 'launcher-build.log'
    $compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
    if (-not (Test-Path -LiteralPath $compiler)) { throw "The Windows .NET Framework C# compiler is missing: $compiler" }

    function Get-LauncherFingerprint {
        # Test fixtures live below Tests and are never included in the application.
        $script:launcherSources = @(Get-ChildItem -LiteralPath $LauncherSourceDirectory -File -Filter '*.cs' | Sort-Object Name)
        if ($script:launcherSources.Count -eq 0) { throw "No launcher sources found: $LauncherSourceDirectory" }
        $lines = @($script:launcherSources | ForEach-Object { $_.Name + ':' + (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash })
        $sha = [Security.Cryptography.SHA256]::Create()
        try { return [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes(($lines -join "`n")))).Replace('-', '') }
        finally { $sha.Dispose() }
    }

    $sha = [Security.Cryptography.SHA256]::Create()
    try { $mutexKey = [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($OutputDirectory.ToUpperInvariant()))).Replace('-', '').Substring(0, 24) }
    finally { $sha.Dispose() }
    $mutex = New-Object Threading.Mutex($false, ('Local\OutOfWindowLauncherBuild-' + $mutexKey))
    $locked = $false
    try {
        try { $locked = $mutex.WaitOne(15000) }
        catch [Threading.AbandonedMutexException] { $locked = $true }
        if (-not $locked) { throw 'Another launch is preparing the launcher. Please retry shortly.' }
        $fingerprint = Get-LauncherFingerprint
        $stamp = $null
        if (Test-Path -LiteralPath $stampFile) {
            try { $stamp = Get-Content -LiteralPath $stampFile -Raw | ConvertFrom-Json } catch { $stamp = $null }
        }
        $current = (Test-Path -LiteralPath $launcher) -and $stamp -and $stamp.sourcesFingerprint -eq $fingerprint
        if ($current) { $current = (Get-FileHash -LiteralPath $launcher -Algorithm SHA256).Hash -eq $stamp.executableSha256 }
        if (-not $current) {
            $temporaryLauncher = Join-Path $OutputDirectory ('launcher-' + [Guid]::NewGuid().ToString('N') + '.exe')
            $compilerArgs = @('/nologo', '/utf8output', '/codepage:65001', '/target:winexe', '/platform:x64', '/optimize+', "/out:$temporaryLauncher",
                '/reference:System.dll', '/reference:System.Core.dll', '/reference:System.Drawing.dll',
                '/reference:System.Windows.Forms.dll', '/reference:System.Web.Extensions.dll')
            $compilerArgs += @($script:launcherSources | ForEach-Object { $_.FullName })
            try {
                & $compiler @compilerArgs 2>&1 | Tee-Object -FilePath $buildLog | Out-Host
                if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $temporaryLauncher)) {
                    throw "Launcher compilation failed (exit $LASTEXITCODE). Log: $buildLog"
                }
                if ((Get-LauncherFingerprint) -ne $fingerprint) { throw 'Launcher sources changed during compilation. Please retry.' }
                # A running older launcher is never terminated to replace its executable.
                Move-Item -LiteralPath $temporaryLauncher -Destination $launcher -Force
                $stamp = [ordered]@{
                    sourcesFingerprint = $fingerprint
                    executableSha256 = (Get-FileHash -LiteralPath $launcher -Algorithm SHA256).Hash
                    builtUtc = [DateTime]::UtcNow.ToString('o')
                }
                [IO.File]::WriteAllText($stampFile, ($stamp | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))
            }
            finally { if (Test-Path -LiteralPath $temporaryLauncher) { Remove-Item -LiteralPath $temporaryLauncher -Force } }
        }
    }
    finally {
        if ($locked) { $mutex.ReleaseMutex() }
        $mutex.Dispose()
    }
    if ($BuildOnly) { Write-Output $launcher; return }
    # The GUI owns its lifetime and errors; this bootstrap does not wait for UE.
    Start-Process -FilePath $launcher -ArgumentList @("--root=`"$RepositoryRoot`"", "--scene=$Scene", "--state-dir=`"$OutputDirectory`"") -WorkingDirectory $RepositoryRoot -WindowStyle Normal | Out-Null
}
catch {
    if ($BuildOnly) { throw }
    $message = $_.Exception.Message
    if ($buildLog) { $message += "`r`n`r`nBuild log: $buildLog" }
    try {
        Add-Type -AssemblyName System.Windows.Forms
        [Windows.Forms.MessageBox]::Show($message, 'Out of Window - launcher error', 'OK', 'Error') | Out-Null
    } catch { Write-Host $message }
    Write-Error -Message $message -ErrorAction Continue
    exit 1
}
