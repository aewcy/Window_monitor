@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist "monitor-agent.exe" (
    echo 未找到 monitor-agent.exe，请确认安装包已完整解压。
    pause
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-service.ps1" -Install
if errorlevel 1 (
    echo.
    echo 安装失败，请查看日志：%ProgramData%\MonitorAgent\install.log
    pause
    exit /b 1
)

echo.
echo MonitorAgent 服务已安装并启动。
echo 可在 Windows 服务列表中搜索 MonitorAgent。
pause
