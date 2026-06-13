@echo off
chcp 65001 >nul
title Monitor Agent

:: ============================================
::  配置区 - 改成你的服务器地址
:: ============================================
set MONITOR_SERVER_HOST=127.0.0.1
set MONITOR_SERVER_PORT=8899
set AGENT_NAME=试验机-01
set SCREENSHOT_INTERVAL=30

:: ============================================
::  环境自检 + 自动配置 (下面不用改)
:: ============================================

cd /d "%~dp0"

echo ============================================
echo   Monitor Agent
echo ============================================

:: --- 1. 检查 Python ---
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python, 请先安装 Python 3.9+
    echo https://www.python.org/downloads/
    pause
    exit /b 1
)
echo [OK] Python 已就绪

:: --- 2. 检查/创建虚拟环境 ---
if not exist "venv\Scripts\python.exe" (
    echo [..] 正在创建虚拟环境...
    python -m venv venv
    if errorlevel 1 (
        echo [错误] 虚拟环境创建失败
        pause
        exit /b 1
    )
    set NEED_INSTALL=1
    echo [OK] 虚拟环境已创建
) else (
    echo [OK] 虚拟环境已就绪
)

:: --- 3. 检查/安装依赖 ---
call venv\Scripts\activate.bat

:: 检测关键包是否已安装
python -c "import mss, requests, psutil" >nul 2>&1
if errorlevel 1 set NEED_INSTALL=1

:: 检测 Windows API
python -c "import win32gui" >nul 2>&1
if errorlevel 1 set NEED_INSTALL=1

if defined NEED_INSTALL (
    echo [..] 正在安装依赖...
    pip install -r requirements.txt --quiet
    pip install pywin32 --quiet
    if errorlevel 1 (
        echo [错误] 依赖安装失败，请检查网络
        pause
        exit /b 1
    )
    echo [OK] 依赖安装完成
) else (
    echo [OK] 依赖已就绪
)

echo ============================================
echo   环境就绪, 启动 Agent...
echo   服务器: %MONITOR_SERVER_HOST%:%MONITOR_SERVER_PORT%
echo   机器名: %AGENT_NAME%
echo ============================================
echo.

python main.py
pause
