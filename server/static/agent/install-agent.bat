@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist "monitor-agent.exe" (
    echo 未找到 monitor-agent.exe，请确认安装包已完整解压。
    pause
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-agent.ps1" -Install
if errorlevel 1 (
    echo.
    echo 安装失败，请查看日志：%LOCALAPPDATA%\Windows Monitor\logs\install.log
    pause
    exit /b 1
)

echo.
echo Windows Monitor 已安装为后台任务并启动。
echo 可在任务管理器中搜索 WindowsMonitor。
pause
