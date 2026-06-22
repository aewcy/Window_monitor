@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist "monitor-agent.exe" (
    echo 未找到 monitor-agent.exe，请确认安装包已完整解压。
    pause
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-service.ps1"
