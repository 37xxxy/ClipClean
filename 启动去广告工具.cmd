@echo off
if exist "%~dp0ClipClean-v0.3.0.exe" (
  start "" "%~dp0ClipClean-v0.3.0.exe" %*
) else (
  start "" "%~dp0ClipClean.exe" %*
)
