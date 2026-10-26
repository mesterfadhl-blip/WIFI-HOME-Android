@echo off
setlocal
cd /d "%~dp0"
"%~dp0runtime\python.exe" -I -S -X utf8 "%~dp0desktop_backup.py"
pause
