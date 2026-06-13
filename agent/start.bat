@echo off
setlocal enabledelayedexpansion
title Monitor Agent

:: ============================================
::  CONFIG - Edit your server info here
:: ============================================
set MONITOR_SERVER_HOST=127.0.0.1
set MONITOR_SERVER_PORT=8899
set AGENT_NAME=PC-01
set SCREENSHOT_INTERVAL=30

:: ============================================
::  AUTO SETUP + LAUNCH (no touch below)
:: ============================================
cd /d "%~dp0"

echo.
echo   ========================================
echo         Monitor Agent  v1.0
echo   ========================================
echo.

:: ---- Step 1: Find Python ----
set PY_OK=0
set PYTHON=

for %%p in (
    python python3 py
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%ProgramFiles%\Python311\python.exe"
    "%ProgramFiles%\Python312\python.exe"
    "%ProgramFiles%\Python313\python.exe"
    "C:\Python311\python.exe"
    "C:\Python312\python.exe"
    "C:\Python313\python.exe"
) do (
    if !PY_OK!==0 (
        "%%~p" --version >nul 2>&1
        if not errorlevel 1 (
            set PYTHON=%%~p
            set PY_OK=1
        )
    )
)

:: ---- Step 2: Auto-install Python if missing ----
if !PY_OK!==0 (
    echo [..] Python not found, auto-installing...

    winget --version >nul 2>&1
    if not errorlevel 1 (
        echo       Installing via winget...
        winget install Python.Python.3.11 --silent --accept-package-agreements --accept-source-agreements
        if not errorlevel 1 goto :recheck
    )

    echo       Opening Python download page...
    powershell -Command "Start-Process 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe'"
    echo.
    echo   [!] In the installer:
    echo       1. CHECK "Add Python to PATH"
    echo       2. Click "Install Now"
    echo       3. Press any key here after done
    pause

    :recheck
    for %%p in (
        "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
        "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
        "%ProgramFiles%\Python311\python.exe"
        "%ProgramFiles%\Python312\python.exe"
        "C:\Python311\python.exe"
        "C:\Python312\python.exe"
    ) do (
        if !PY_OK!==0 (
            "%%~p" --version >nul 2>&1
            if not errorlevel 1 (
                set PYTHON=%%~p
                set PY_OK=1
            )
        )
    )

    if !PY_OK!==0 (
        echo   [X] Python still not found.
        echo       Install manually: https://www.python.org/downloads/
        pause
        exit /b 1
    )
)

!PYTHON! --version
echo   [OK] Python ready

:: ---- Step 3: Create venv ----
if not exist "venv\Scripts\python.exe" (
    echo [..] Creating virtual environment...
    "!PYTHON!" -m venv venv
    if errorlevel 1 (
        echo   [X] Failed to create venv
        pause & exit /b 1
    )
    set REINSTALL=1
    echo   [OK] venv created
) else (
    echo   [OK] venv ready
)

:: ---- Step 4: Install dependencies ----
call venv\Scripts\activate.bat >nul

python -c "import mss, requests, psutil, win32gui" >nul 2>&1
if errorlevel 1 set REINSTALL=1

if defined REINSTALL (
    echo [..] Installing packages...
    pip install --quiet --disable-pip-version-check mss Pillow psutil requests pywin32

    python -c "import mss, requests, psutil, win32gui" >nul 2>&1
    if errorlevel 1 (
        echo   [X] Install failed. Check network.
        pause & exit /b 1
    )
    echo   [OK] Packages installed
) else (
    echo   [OK] Packages ready
)

:: ---- Step 5: Launch Agent ----
echo.
echo   ========================================
echo   Server  : !MONITOR_SERVER_HOST!:!MONITOR_SERVER_PORT!
echo   Agent   : !AGENT_NAME!
echo   Screenshot interval : !SCREENSHOT_INTERVAL!s
echo   ========================================
echo.

python main.py
pause
