@echo off
setlocal
cd /d "%~dp0"
py -3 -c "import sys; assert sys.version_info >= (3,11)" >nul 2>&1
if not errorlevel 1 (
    py -3 -m erp.launch
    goto finished
)
python -c "import sys; assert sys.version_info >= (3,11)" >nul 2>&1
if not errorlevel 1 (
    python -m erp.launch
    goto finished
)
echo Python 3.11 or newer is required.
echo Install Python from the official page, then open this file again.
echo During installation select: Add Python to PATH.
start "" "https://www.python.org/downloads/windows/"
:finished
pause
