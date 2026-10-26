@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0runtime\python.exe" (
    echo Extract the entire ZIP folder first. The bundled Python runtime is missing.
    pause
    exit /b 1
)
"%~dp0runtime\python.exe" -I -S -X utf8 "%~dp0desktop_start.py"
if errorlevel 1 (
    echo Please keep the error window and send its message.
    pause
)
