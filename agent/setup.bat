@echo off
chcp 65001 >nul
title Monitor Agent - 初始化安装

cd /d "%~dp0"

echo ============================================
echo   Monitor Agent - 一键安装
echo ============================================
echo.

:: 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.9+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/3] Python 已找到
python --version

:: 创建虚拟环境
if not exist "venv" (
    echo [2/3] 创建虚拟环境...
    python -m venv venv
) else (
    echo [2/3] 虚拟环境已存在，跳过
)

:: 安装依赖
echo [3/3] 安装依赖...
call venv\Scripts\activate.bat
pip install -r requirements.txt --quiet
pip install pywin32 --quiet

echo.
echo ============================================
echo   安装完成！
echo   双击 start.bat 启动 Agent
echo ============================================
pause
