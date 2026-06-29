@echo off
chcp 65001 >nul
echo ============================================
echo   Monitor Agent - PyInstaller 打包
echo   输出: agent\dist\monitor-agent.exe
echo ============================================
echo.

cd /d "%~dp0"

echo [1/4] 检查 PyInstaller ...
pip show pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo   [!] PyInstaller 未安装，正在安装...
    pip install pyinstaller
    if %errorlevel% neq 0 (
        echo   [x] PyInstaller 安装失败
        pause
        exit /b 1
    )
)
echo   [OK] PyInstaller 已就绪

echo [2/4] 安装/检查 Agent 依赖 ...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo   [x] Agent 依赖安装失败
    pause
    exit /b 1
)

echo [3/4] 清理旧构建 ...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [4/4] 构建 monitor-agent.exe ...
pyinstaller --clean --noconfirm agent.spec
if %errorlevel% neq 0 (
    echo.
    echo [x] 构建失败
    pause
    exit /b 1
)

if not exist "..\server\static\agent" mkdir "..\server\static\agent"
copy /y "dist\monitor-agent.exe" "..\server\static\agent\monitor-agent.exe" >nul
if %errorlevel% neq 0 (
    echo [x] 同步到 server\static\agent 失败
    pause
    exit /b 1
)
copy /y "install-agent.bat" "..\server\static\agent\install-agent.bat" >nul
copy /y "uninstall-agent.bat" "..\server\static\agent\uninstall-agent.bat" >nul
copy /y "install-agent.ps1" "..\server\static\agent\install-agent.ps1" >nul
copy /y "updater.ps1" "..\server\static\agent\updater.ps1" >nul

echo.
echo ============================================
echo   构建成功
echo   本地输出: agent\dist\monitor-agent.exe
echo   网页下载: server\static\agent\monitor-agent.exe
echo   下载接口会自动打包 exe + 服务安装脚本
echo ============================================
pause
