@echo off
chcp 65001 >nul
title Monitor Agent

:: ============================================
::  配置区 — 只改这里
:: ============================================
set MONITOR_SERVER_HOST=127.0.0.1
set MONITOR_SERVER_PORT=8899
set AGENT_NAME=试验机-01
set SCREENSHOT_INTERVAL=30
:: Python 版本 (如需自动安装: 311 / 312 / 313)
set PY_VER=3.11

:: ============================================
::  一键环境配置 + 启动 (下面全自动)
:: ============================================
cd /d "%~dp0"

echo.
echo   ╔══════════════════════════════════════╗
echo   ║        Monitor Agent  v1.0          ║
echo   ╚══════════════════════════════════════╝
echo.

:: ==========================================
:: Step 1 — 找 Python
:: ==========================================
set PYTHON=
set PY_OK=0

:: 候选路径
for %%p in (
    python
    python3
    py
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
    if %PY_OK%==0 (
        "%%~p" --version >nul 2>&1
        if not errorlevel 1 (
            set PYTHON=%%~p
            set PY_OK=1
        )
    )
)

:: ==========================================
:: Step 2 — 没 Python 就自动装
:: ==========================================
if %PY_OK%==0 (
    echo [..] 未找到 Python %PY_VER%，正在自动安装...
    echo.

    :: 尝试 winget (Windows 10+ 自带)
    winget --version >nul 2>&1
    if not errorlevel 1 (
        echo       通过 winget 安装 Python %PY_VER% ...
        winget install Python.Python.%PY_VER% --silent --accept-package-agreements --accept-source-agreements
        if not errorlevel 1 (
            goto :python_installed
        )
    )

    :: 回退 — PowerShell 下载安装
    echo       通过浏览器下载安装...
    powershell -Command "Start-Process 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe'"
    echo.
    echo   [!] 请在弹出的安装程序中:
    echo       1. 勾选 "Add Python to PATH"
    echo       2. 点击 Install Now
    echo       3. 安装完成后关闭安装窗口
    echo       4. 回到这里按任意键继续
    pause

    :: 重新定位 Python
    for %%p in (
        "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
        "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
        "%ProgramFiles%\Python311\python.exe"
        "%ProgramFiles%\Python312\python.exe"
        "C:\Python311\python.exe"
        "C:\Python312\python.exe"
    ) do (
        if %PY_OK%==0 (
            "%%~p" --version >nul 2>&1
            if not errorlevel 1 (
                set PYTHON=%%~p
                set PY_OK=1
            )
        )
    )

    if %PY_OK%==0 (
        echo   [X] Python 仍未找到，请手动安装后重试。
        echo       https://www.python.org/downloads/
        pause
        exit /b 1
    )
)

:python_installed
"%PYTHON%" --version
echo   [OK] Python 就绪

:: ==========================================
:: Step 3 — 创建虚拟环境
:: ==========================================
if not exist "venv\Scripts\python.exe" (
    echo [..] 创建虚拟环境...
    "%PYTHON%" -m venv venv
    if errorlevel 1 (
        echo   [X] 虚拟环境创建失败
        pause & exit /b 1
    )
    set REINSTALL=1
    echo   [OK] 虚拟环境已创建
) else (
    echo   [OK] 虚拟环境已就绪
)

:: ==========================================
:: Step 4 — 安装/更新依赖
:: ==========================================
call venv\Scripts\activate.bat

:: 快速完整性检查
python -c "import mss, requests, psutil, win32gui" >nul 2>&1
if errorlevel 1 set REINSTALL=1

if defined REINSTALL (
    echo [..] 安装依赖包...
    pip install --quiet --disable-pip-version-check -r requirements.txt
    pip install --quiet --disable-pip-version-check pywin32
    :: 二次验证
    python -c "import mss, requests, psutil, win32gui" >nul 2>&1
    if errorlevel 1 (
        echo   [X] 依赖安装失败，请检查网络后重试
        pause & exit /b 1
    )
    echo   [OK] 依赖安装完成
) else (
    echo   [OK] 依赖已就绪
)

:: ==========================================
:: Step 5 — 启动
:: ==========================================
echo.
echo   ═══════════════════════════════════════
echo   Agent 启动中...
echo   服务器 : %MONITOR_SERVER_HOST%:%MONITOR_SERVER_PORT%
echo   机器名 : %AGENT_NAME%
echo   截图间隔: %SCREENSHOT_INTERVAL%s
echo   ═══════════════════════════════════════
echo.

python main.py
pause
