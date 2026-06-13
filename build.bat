@echo off
chcp 65001 >nul
echo ============================================
echo   Monitor Agent — PyInstaller 打包
echo   输出: dist\monitor-agent.exe (单文件)
echo ============================================
echo.

cd /d "%~dp0"

REM 检查依赖
echo [1/3] 检查环境...
pip show pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo   [!] PyInstaller 未安装, 正在安装...
    pip install pyinstaller
    if %errorlevel% neq 0 (
        echo   [✗] PyInstaller 安装失败
        pause
        exit /b 1
    )
)
echo   [✓] PyInstaller OK

REM 确保 agent 依赖已安装 (用于分析)
pip install -r agent\requirements.txt >nul 2>&1

REM 清理旧构建
echo [2/3] 清理旧构建...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist agent\*.spec.orig del agent\*.spec.orig

REM 构建
echo [3/3] 构建 monitor-agent.exe ...
echo   (可能需要 1-2 分钟)...
echo.
pyinstaller --clean --noconfirm agent\agent.spec

if %errorlevel% neq 0 (
    echo.
    echo [✗] 构建失败!
    pause
    exit /b 1
)

echo.
echo ============================================
echo   构建成功!
echo   输出: dist\monitor-agent.exe
echo.
echo   部署方式: 将 dist\monitor-agent.exe 复制到被控机直接运行
echo ============================================
pause
