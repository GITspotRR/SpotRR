@echo off
cd /d "%~dp0"

:: Use venv if available (created by setup.bat), otherwise system Python
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\pythonw.exe spotrr.py
) else (
    echo  Virtual environment not found.
    echo  Running setup first...
    echo.
    call setup.bat
)
