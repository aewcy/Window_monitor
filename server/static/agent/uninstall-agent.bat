@echo off
chcp 65001 >nul
cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-agent.ps1" -Remove
if errorlevel 1 (
    echo.
    echo 卸载失败，请查看日志：%LOCALAPPDATA%\GameFrameRateViewer\logs\install.log
    pause
    exit /b 1
)

echo.
echo GameFrameRateViewer 已卸载。
pause
