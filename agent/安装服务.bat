@echo off
chcp 65001 >nul
echo ========================================
echo   Monitor Agent 安装器
echo ========================================
echo.

:: 检查管理员权限
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] 需要管理员权限，正在请求提权...
    powershell.exe -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

echo [OK] 管理员权限已获取
echo [1/2] 正在启动安装界面...
echo.

:: 以管理员身份运行 PowerShell GUI
powershell.exe -ExecutionPolicy Bypass -WindowStyle Normal -File "%~dp0install-service.ps1"

if %errorlevel% neq 0 (
    echo.
    echo [!] 安装器异常退出，错误码: %errorlevel%
    echo.
    pause
)
