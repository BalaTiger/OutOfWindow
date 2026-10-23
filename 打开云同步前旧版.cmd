@echo off
powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%~dp0unreal\Launch-Unreal.ps1" -OutputDirectory "%~dp0.runtime\launcher-versions\rollback-before-cloud-20261019"
