@echo off
setlocal enabledelayedexpansion
title SpotRR Update
color 0A
cls

set "DIR=%~dp0"
cd /d "%DIR%" 2>nul
if errorlevel 1 (
    echo  [ERROR] Cannot access the script folder: %DIR%
    echo  Move the folder to a local drive and try again.
    pause & exit /b 1
)

echo.
echo  =====================================================
echo    SPOTRR  ^|  Update
echo  =====================================================
echo.
echo  Updates the app code in place, then re-runs setup.
echo  Your settings.json, downloads and virtualenv are kept.
echo.

set "REPO=GITspotRR/SpotRR"
set "BRANCH=main"
set "REPO_URL=https://github.com/%REPO%"
set "RAW_ZIP=https://codeload.github.com/%REPO%/zip/refs/heads/%BRANCH%"

:: ── 1. Install via git?  git pull is cleanest ───────────────────────────────
if exist ".git" (
    where git >nul 2>&1
    if not errorlevel 1 (
        echo  [..] Updating via git...
        git pull --ff-only origin %BRANCH%
        if errorlevel 1 (
            echo.
            echo  [ERROR] git pull failed.
            echo          You probably have local changes or git is not configured.
            echo          Fix:  git pull  manually, or download the ZIP from %REPO_URL%
            echo.
            pause & exit /b 1
        )
        echo  [OK] Code updated via git
        goto :setup
    )
    echo  [WARN] git not found on this PC — falling back to ZIP download.
)

:: ── 2. ZIP install — download and replace code in place ─────────────────────
echo  [..] Downloading latest version from GitHub...
set "TMPZIP=%TEMP%\SpotRR_update.zip"
set "TMPDIR=%TEMP%\SpotRR_update"

del "%TMPZIP%" >nul 2>&1
powershell -NoProfile -Command "Invoke-WebRequest -Uri '%RAW_ZIP%' -OutFile '%TMPZIP%'" >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [ERROR] Download failed. Check your internet connection.
    echo          Manual update: download the ZIP from %REPO_URL%
    echo          and copy the new files over this folder.
    echo.
    pause & exit /b 1
)

if exist "%TMPDIR%" rmdir /s /q "%TMPDIR%"
powershell -NoProfile -Command "Expand-Archive -LiteralPath '%TMPZIP%' -DestinationPath '%TMPDIR%' -Force" >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [ERROR] Could not unzip the downloaded update.
    echo.
    pause & exit /b 1
)

set "SRC=%TMPDIR%\SpotRR-%BRANCH%"
if not exist "%SRC%\spotrr.py" (
    echo  [ERROR] Unexpected archive layout — update aborted, nothing was overwritten.
    del "%TMPZIP%" >nul 2>&1
    rmdir /s /q "%TMPDIR%" >nul 2>&1
    pause & exit /b 1
)

echo  [..] Replacing program files (settings.json, downloads, .venv are kept)...
xcopy "%SRC%" "%DIR%" /E /Y /Q /I /H /R >nul
set "XCOPY_ERR=%ERRORLEVEL%"

del "%TMPZIP%" >nul 2>&1
rmdir /s /q "%TMPDIR%" >nul 2>&1

if not "%XCOPY_ERR%"=="0" (
    echo  [WARN] Some files could not be replaced (the app may be running).
    echo         Close SpotRR and run update.bat again if needed.
) else (
    echo  [OK] Code updated
)

:: ── 3. Re-run setup: installs changed deps + launches the app ───────────────
:setup
echo.
echo  =====================================================
echo    Running setup to update dependencies...
echo  =====================================================
echo.
call "setup.bat"