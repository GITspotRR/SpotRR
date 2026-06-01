@echo off
setlocal enabledelayedexpansion
title SpotRR Setup
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
echo    SPOTRR  ^|  Setup ^& Launch
echo  =====================================================
echo.

:: ── Python ───────────────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    :: Try winget auto-install (Windows 10 2004+ with App Installer)
    where winget >nul 2>&1
    if not errorlevel 1 (
        echo  [..] Python not found — installing via winget...
        winget install --id Python.Python.3.12 --silent --accept-source-agreements --accept-package-agreements
        if not errorlevel 1 (
            echo.
            echo  [OK] Python installed.  Please close this window and run setup.bat again.
            echo.
            pause & exit /b 0
        )
    )
    echo  [ERROR] Python 3.10+ is required but was not found.
    echo.
    echo  Install from:  https://www.python.org/downloads/
    echo  IMPORTANT: tick "Add Python to PATH" during installation,
    echo  then run this setup again.
    echo.
    pause & exit /b 1
)

:: Detect Microsoft Store stub (exits with code 9009)
python -c "import sys; sys.exit(0)" >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python found but appears to be the Windows Store stub.
    echo.
    echo  Install the real Python from:  https://www.python.org/downloads/
    echo  IMPORTANT: tick "Add Python to PATH" during installation.
    echo  Then disable the alias: Settings ^> App execution aliases
    echo.
    pause & exit /b 1
)

for /f "tokens=2" %%V in ('python --version 2^>^&1') do set "PY_VER=%%V"
echo  [OK] Python %PY_VER%

for /f "tokens=1,2 delims=." %%A in ("%PY_VER%") do (
    set "PY_MAJOR=%%A"
    set "PY_MINOR=%%B"
)
if %PY_MAJOR% LSS 3 (
    echo  [ERROR] Python 3.10+ required ^(found %PY_VER%^)
    pause & exit /b 1
)
if %PY_MAJOR% EQU 3 if %PY_MINOR% LSS 10 (
    echo  [ERROR] Python 3.10+ required ^(found %PY_VER%^)
    pause & exit /b 1
)

:: ── Virtual environment ───────────────────────────────────────────────────────
set "VENV_PY=%DIR%.venv\Scripts\python.exe"
set "VENV_PYW=%DIR%.venv\Scripts\pythonw.exe"

set "VENV_OK=0"
if exist "%VENV_PY%" (
    "%VENV_PY%" -m pip --version >nul 2>&1
    if not errorlevel 1 set "VENV_OK=1"
)

if "!VENV_OK!"=="0" (
    if exist ".venv\" (
        echo  [..] Existing virtual environment is broken — recreating...
        rmdir /s /q ".venv" >nul 2>&1
    ) else (
        echo  [..] Creating virtual environment...
    )
    python -m venv .venv
    if errorlevel 1 (
        echo  [ERROR] Could not create virtual environment.
        echo  Try: python -m pip install --upgrade virtualenv
        pause & exit /b 1
    )
    echo  [OK] Virtual environment created
) else (
    echo  [OK] Virtual environment ready
)

:: ── pip ───────────────────────────────────────────────────────────────────────
echo  [..] Ensuring pip is up to date...
"%VENV_PY%" -m pip install --upgrade pip --quiet --disable-pip-version-check >nul 2>&1
echo  [OK] pip ready

:: ── Dependencies ─────────────────────────────────────────────────────────────
:: Skip install if requirements.txt is unchanged (faster re-runs)
set "HASH_FILE=.venv\.req_hash"
set "NEED_INSTALL=1"

for /f "skip=1 tokens=*" %%H in ('certutil -hashfile "requirements.txt" MD5 2^>nul') do (
    if not defined REQ_HASH (
        set "RAW=%%H"
        set "REQ_HASH=!RAW: =!"
    )
)

if defined REQ_HASH if exist "%HASH_FILE%" (
    set /p STORED_HASH=<"%HASH_FILE%"
    set "STORED_HASH=!STORED_HASH: =!"
    if "!REQ_HASH!"=="!STORED_HASH!" set "NEED_INSTALL=0"
)

if "!NEED_INSTALL!"=="1" (
    echo  [..] Installing packages ^(first run takes a few minutes^)...
    "%VENV_PY%" -m pip install -r requirements.txt --quiet --prefer-binary --disable-pip-version-check 2>nul
    if errorlevel 1 (
        echo.
        echo  [ERROR] Package installation failed.
        echo.
        echo  Common causes:
        echo    - No internet connection
        echo    - Firewall or proxy blocking pip
        echo    - Antivirus interfering
        echo.
        echo  Try running this script again. If it keeps failing:
        echo    "%VENV_PY%" -m pip install -r requirements.txt
        echo.
        pause & exit /b 1
    )
    if defined REQ_HASH echo !REQ_HASH!>"%HASH_FILE%"
    echo  [OK] Packages installed
) else (
    echo  [OK] Packages up to date
)

:: ── FFmpeg ────────────────────────────────────────────────────────────────────
set "FFMPEG_OK=0"
where ffmpeg >nul 2>&1
if not errorlevel 1 set "FFMPEG_OK=1"
if exist "%USERPROFILE%\.spotdl\ffmpeg.exe"              set "FFMPEG_OK=1"
if exist "%USERPROFILE%\.config\spotdl\ffmpeg.exe"       set "FFMPEG_OK=1"
if exist "%USERPROFILE%\AppData\Local\spotdl\ffmpeg.exe" set "FFMPEG_OK=1"

if "!FFMPEG_OK!"=="0" (
    echo  [..] Downloading FFmpeg ^(one-time setup, ~50 MB, please wait^)...
    "%VENV_PY%" -m spotdl --download-ffmpeg
    if exist "%USERPROFILE%\.spotdl\ffmpeg.exe"              set "FFMPEG_OK=1"
    if exist "%USERPROFILE%\.config\spotdl\ffmpeg.exe"       set "FFMPEG_OK=1"
    if exist "%USERPROFILE%\AppData\Local\spotdl\ffmpeg.exe" set "FFMPEG_OK=1"
    if "!FFMPEG_OK!"=="0" (
        echo  [WARN] FFmpeg download failed.
        echo         WAV and FLAC downloads will not work without it.
        echo         Fix: run  "%VENV_PY%" -m spotdl --download-ffmpeg
        echo         Or install from https://ffmpeg.org and add to PATH.
    ) else (
        echo  [OK] FFmpeg downloaded and ready
    )
) else (
    echo  [OK] FFmpeg ready
)

:: ── Desktop shortcut ─────────────────────────────────────────────────────────
:: Read real Desktop path from registry (handles any locale + OneDrive).
set "DESKTOP=%USERPROFILE%\Desktop"
for /f "tokens=2*" %%A in ('reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders" /v Desktop 2^>nul ^| findstr /i "REG_"') do set "DESKTOP=%%B"

set "SCRIPT=%DIR%spotrr.py"
set "ICON=%DIR%assets\icon.ico"
set "LNK=%DESKTOP%\SpotRR.lnk"

:: Skip shortcut creation if Windows Script Host is disabled (corporate policy).
:: Attempting cscript when WSH is disabled shows a blocking dialog.
set "WSH_OK=1"
for /f "tokens=2*" %%A in ('reg query "HKCU\Software\Microsoft\Windows Script Host\Settings" /v Enabled 2^>nul ^| findstr /i "REG_"') do if "%%B"=="0x0" set "WSH_OK=0"
for /f "tokens=2*" %%A in ('reg query "HKLM\Software\Microsoft\Windows Script Host\Settings" /v Enabled 2^>nul ^| findstr /i "REG_"') do if "%%B"=="0x0" set "WSH_OK=0"

if "!WSH_OK!"=="1" if not exist "%LNK%" (
    if exist "%VENV_PYW%" (set "LAUNCH_EXE=%VENV_PYW%") else (set "LAUNCH_EXE=%VENV_PY%")

    set "SC_VBS=%DIR%_sc_tmp.vbs"
    (
        echo On Error Resume Next
        echo Set sh = CreateObject("WScript.Shell")
        echo Set lnk = sh.CreateShortcut^("%LNK%"^)
        echo lnk.TargetPath = "!LAUNCH_EXE!"
        echo lnk.Arguments = Chr^(34^) ^& "!SCRIPT!" ^& Chr^(34^)
        echo lnk.WorkingDirectory = "%DIR%"
        echo lnk.IconLocation = "%ICON%"
        echo lnk.Description = "SpotRR"
        echo lnk.WindowStyle = 1
        echo lnk.Save
    ) > "!SC_VBS!"
    if exist "!SC_VBS!" (
        cscript //NoLogo "!SC_VBS!" >nul 2>&1
        del "!SC_VBS!" >nul 2>&1
    )
)

if exist "%LNK%" (
    echo  [OK] Desktop shortcut ready
) else (
    echo  [WARN] Could not create desktop shortcut ^(non-critical^)
)

:: ── Launch ────────────────────────────────────────────────────────────────────
echo.
echo  =====================================================
echo    All done!  Launching SpotRR...
echo  =====================================================
echo.

if exist "%VENV_PYW%" (
    start "" "%VENV_PYW%" "%SCRIPT%"
) else (
    start "" "%VENV_PY%" "%SCRIPT%"
)

exit
