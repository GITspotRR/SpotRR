@echo off
title SpotRR — Easy Setup
color 0A
cls

echo.
echo  =====================================================
echo    SPOTRR  ^|  Easy Setup
echo  =====================================================
echo.

:: ── Check Python ──────────────────────────────────────────────────────────────
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] Python is not installed or not in PATH.
    echo.
    echo  Please install Python 3.10 or newer from:
    echo    https://www.python.org/downloads/
    echo.
    echo  IMPORTANT: Check "Add Python to PATH" during install.
    echo.
    pause
    exit /b 1
)
for /f "tokens=2" %%V in ('python --version 2^>^&1') do set PY_VER=%%V
echo  [OK] Python %PY_VER% found

:: ── Create virtual environment ────────────────────────────────────────────────
if not exist ".venv" (
    echo  [..] Creating virtual environment...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo  [ERROR] Could not create virtual environment.
        pause
        exit /b 1
    )
    echo  [OK] Virtual environment created
) else (
    echo  [OK] Virtual environment already exists
)

:: ── Install dependencies ──────────────────────────────────────────────────────
echo  [..] Installing dependencies (first time may take a few minutes)...
.venv\Scripts\pip install -r requirements.txt --quiet --disable-pip-version-check
if %errorlevel% neq 0 (
    echo  [ERROR] Failed to install dependencies.
    echo         Check your internet connection and try again.
    pause
    exit /b 1
)
echo  [OK] All dependencies installed

:: ── Download FFmpeg ───────────────────────────────────────────────────────────
set "FFMPEG_PATH=%USERPROFILE%\.config\spotdl\ffmpeg.exe"
if not exist "%FFMPEG_PATH%" (
    echo  [..] Downloading FFmpeg (one-time download)...
    .venv\Scripts\python -m spotdl --download-ffmpeg
    if exist "%FFMPEG_PATH%" (
        echo  [OK] FFmpeg downloaded
    ) else (
        echo  [WARN] FFmpeg download may have failed — the app will retry on launch.
    )
) else (
    echo  [OK] FFmpeg already installed
)

:: ── Create desktop shortcut ───────────────────────────────────────────────────
echo  [..] Creating desktop shortcut...

set "SCRIPT_DIR=%~dp0"
set "RUN_BAT=%SCRIPT_DIR%run.bat"
set "ICON_PATH=%SCRIPT_DIR%assets\icon.ico"
set "SHORTCUT=%USERPROFILE%\Desktop\SpotRR.lnk"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s = (New-Object -COM WScript.Shell).CreateShortcut('%SHORTCUT%');" ^
  "$s.TargetPath = '%RUN_BAT%';" ^
  "$s.WorkingDirectory = '%SCRIPT_DIR%';" ^
  "$s.IconLocation = '%ICON_PATH%';" ^
  "$s.Description = 'SpotRR';" ^
  "$s.WindowStyle = 1;" ^
  "$s.Save()"

if exist "%SHORTCUT%" (
    echo  [OK] Shortcut created on Desktop
) else (
    echo  [WARN] Could not create shortcut automatically.
    echo         You can create it manually from the app (toolbar ^> Shortcut).
)

:: ── Done ──────────────────────────────────────────────────────────────────────
echo.
echo  =====================================================
echo    Setup complete!  Launching SpotRR...
echo  =====================================================
echo.
timeout /t 2 /nobreak >nul
start "" "%RUN_BAT%"
