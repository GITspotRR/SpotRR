@echo off
setlocal enabledelayedexpansion
title SpotRR — Setup
color 0A
cls

:: ── Always run from the directory that contains this script ──────────────────
set "DIR=%~dp0"
cd /d "%DIR%"

echo.
echo  =====================================================
echo    SPOTRR  ^|  Setup ^& Launch
echo  =====================================================
echo.

:: ── Python ────────────────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found.
    echo.
    echo  Install Python 3.10+ from:  https://www.python.org/downloads/
    echo  IMPORTANT: check "Add Python to PATH" during install.
    echo.
    pause & exit /b 1
)
for /f "tokens=2" %%V in ('python --version 2^>^&1') do set "PY_VER=%%V"
echo  [OK] Python %PY_VER%

:: ── Virtual environment ───────────────────────────────────────────────────────
if not exist ".venv\Scripts\python.exe" (
    echo  [..] Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 ( echo  [ERROR] Could not create virtual environment. & pause & exit /b 1 )
    echo  [OK] Virtual environment created
) else (
    echo  [OK] Virtual environment ready
)

:: ── Dependencies — skip if requirements.txt has not changed ──────────────────
set "HASH_FILE=.venv\.req_hash"
set "NEED_INSTALL=1"
for /f "usebackq delims=" %%H in (`powershell -NoProfile -Command "(Get-FileHash 'requirements.txt' -Algorithm MD5).Hash" 2^>nul`) do set "REQ_HASH=%%H"
if defined REQ_HASH (
    if exist "%HASH_FILE%" (
        set /p STORED_HASH=<"%HASH_FILE%"
        if "!REQ_HASH!"=="!STORED_HASH!" set "NEED_INSTALL=0"
    )
)
if "!NEED_INSTALL!"=="1" (
    echo  [..] Installing packages ^(first run takes a few minutes^)...
    .venv\Scripts\pip install -r requirements.txt --quiet --prefer-binary --disable-pip-version-check
    if errorlevel 1 ( echo  [ERROR] Package install failed. Check your internet connection. & pause & exit /b 1 )
    if defined REQ_HASH echo !REQ_HASH!>"%HASH_FILE%"
    echo  [OK] Packages installed
) else (
    echo  [OK] Packages up to date
)

:: ── FFmpeg ────────────────────────────────────────────────────────────────────
set "FFMPEG=%USERPROFILE%\.config\spotdl\ffmpeg.exe"
if not exist "%FFMPEG%" (
    echo  [..] Downloading FFmpeg ^(one-time, may take a moment^)...
    .venv\Scripts\python -m spotdl --download-ffmpeg >nul 2>&1
    if exist "%FFMPEG%" ( echo  [OK] FFmpeg ready ) else ( echo  [WARN] FFmpeg download may have failed — app will retry on launch )
) else (
    echo  [OK] FFmpeg ready
)

:: ── Desktop shortcut — target pythonw.exe directly (no extra launcher) ───────
set "PYTHONW=%DIR%.venv\Scripts\pythonw.exe"
set "SCRIPT=%DIR%spotrr.py"
set "ICON=%DIR%assets\icon.ico"

:: Get the real Desktop path (works even when Desktop is inside OneDrive)
for /f "usebackq delims=" %%D in (`powershell -NoProfile -Command "[Environment]::GetFolderPath('Desktop')"`) do set "DESKTOP=%%D"
if not defined DESKTOP set "DESKTOP=%USERPROFILE%\Desktop"
set "LNK=%DESKTOP%\SpotRR.lnk"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$q=[char]34;$s=(New-Object -COM WScript.Shell).CreateShortcut('%LNK%');$s.TargetPath='%PYTHONW%';$s.Arguments=$q+'%SCRIPT%'+$q;$s.WorkingDirectory='%DIR%';$s.IconLocation='%ICON%';$s.Description='SpotRR';$s.WindowStyle=1;$s.Save()" 2>nul

if exist "%LNK%" (
    echo  [OK] Desktop shortcut created
) else (
    echo  [WARN] Could not create shortcut — create it manually from the app toolbar
)

:: ── Launch ────────────────────────────────────────────────────────────────────
echo.
echo  =====================================================
echo    Ready!  Launching SpotRR...
echo  =====================================================
echo.
start "" "%PYTHONW%" "%SCRIPT%"
exit
