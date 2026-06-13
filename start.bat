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
::  启动 (下面不用改)
:: ============================================

cd /d "%~dp0"

:: 检查虚拟环境
if not exist "agent\venv\Scripts\activate.bat" (
    echo [提示] 首次运行，请先双击 setup.bat 初始化
    pause
    exit /b 1
)

:: 激活虚拟环境并启动
call agent\venv\Scripts\activate.bat
python agent\main.py
pause
