@echo off
setlocal enabledelayedexpansion
title SpotRR Setup
color 0A
cls

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
    echo  Check "Add Python to PATH" during install.
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
for /f "skip=1 tokens=*" %%H in ('certutil -hashfile "requirements.txt" MD5 2^>nul') do (
    if not defined REQ_HASH set "REQ_HASH=%%H"
)
if defined REQ_HASH if exist "%HASH_FILE%" (
    set /p STORED_HASH=<"%HASH_FILE%"
    if "!REQ_HASH!"=="!STORED_HASH!" set "NEED_INSTALL=0"
)
if "!NEED_INSTALL!"=="1" (
    echo  [..] Installing packages ^(first run takes a few minutes^)...
    .venv\Scripts\pip install -r requirements.txt --quiet --prefer-binary --disable-pip-version-check
    if errorlevel 1 ( echo  [ERROR] Install failed. Check internet connection. & pause & exit /b 1 )
    if defined REQ_HASH echo !REQ_HASH!>"%HASH_FILE%"
    echo  [OK] Packages installed
) else (
    echo  [OK] Packages up to date
)

:: ── FFmpeg — check system PATH and both spotdl storage locations ─────────────
where ffmpeg >nul 2>&1
if not errorlevel 1 goto :ffmpeg_ok
if exist "%USERPROFILE%\.spotdl\ffmpeg.exe"        goto :ffmpeg_ok
if exist "%USERPROFILE%\.config\spotdl\ffmpeg.exe" goto :ffmpeg_ok
echo  [..] Downloading FFmpeg ^(one-time, please wait^)...
.venv\Scripts\python -m spotdl --download-ffmpeg
:ffmpeg_ok
echo  [OK] FFmpeg ready

:: ── Desktop path — handles OneDrive Desktop relocation ───────────────────────
set "DESKTOP=%USERPROFILE%\Desktop"
if not exist "%DESKTOP%\" (
    for /d %%D in ("%USERPROFILE%\OneDrive*") do (
        if exist "%%D\Desktop\" set "DESKTOP=%%D\Desktop"
    )
)

:: ── Desktop shortcut — cscript VBS (no PowerShell, no ( ) block issues) ──────
set "PYTHONW=%DIR%.venv\Scripts\pythonw.exe"
set "SCRIPT=%DIR%spotrr.py"
set "ICON=%DIR%assets\icon.ico"
set "LNK=%DESKTOP%\SpotRR.lnk"

if exist "%LNK%" goto :shortcut_done

set "SC_VBS=%TEMP%\spotrr_sc.vbs"
echo Set sh = CreateObject("WScript.Shell")              > "%SC_VBS%"
echo Set lnk = sh.CreateShortcut("%LNK%")               >> "%SC_VBS%"
echo lnk.TargetPath = "%PYTHONW%"                       >> "%SC_VBS%"
echo lnk.Arguments = Chr(34) ^& "%SCRIPT%" ^& Chr(34)  >> "%SC_VBS%"
echo lnk.WorkingDirectory = "%DIR%"                     >> "%SC_VBS%"
echo lnk.IconLocation = "%ICON%"                        >> "%SC_VBS%"
echo lnk.Description = "SpotRR"                        >> "%SC_VBS%"
echo lnk.WindowStyle = 1                               >> "%SC_VBS%"
echo lnk.Save                                          >> "%SC_VBS%"
cscript //NoLogo "%SC_VBS%" >nul 2>&1
del "%SC_VBS%" >nul 2>&1

:shortcut_done
if exist "%LNK%" ( echo  [OK] Desktop shortcut ready ) else ( echo  [WARN] Could not create shortcut )

:: ── Launch ────────────────────────────────────────────────────────────────────
echo.
echo  =====================================================
echo    All done!  Launching SpotRR...
echo  =====================================================
echo.
start "" "%PYTHONW%" "%SCRIPT%"
exit
