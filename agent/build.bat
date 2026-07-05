@echo off
setlocal
chcp 65001 >nul

cd /d "%~dp0"

echo ============================================
echo   Monitor Agent - PyInstaller build
echo   Output: agent\dist\monitor-agent.exe
echo ============================================
echo.

echo [1/4] Check PyInstaller
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo PyInstaller is missing, installing...
    pip install pyinstaller
    if errorlevel 1 exit /b 1
)

echo [2/4] Install/check dependencies
pip install -r requirements.txt
if errorlevel 1 exit /b 1

echo [3/4] Clean old build
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [4/4] Build executable
pyinstaller --clean --noconfirm agent.spec
if errorlevel 1 exit /b 1

if not exist "..\server\static\agent" mkdir "..\server\static\agent"
copy /y "dist\monitor-agent.exe" "..\server\static\agent\monitor-agent.exe" >nul
if errorlevel 1 exit /b 1
copy /y "install-agent.bat" "..\server\static\agent\install-agent.bat" >nul
if errorlevel 1 exit /b 1
copy /y "uninstall-agent.bat" "..\server\static\agent\uninstall-agent.bat" >nul
if errorlevel 1 exit /b 1
copy /y "install-agent.ps1" "..\server\static\agent\install-agent.ps1" >nul
if errorlevel 1 exit /b 1
copy /y "updater.ps1" "..\server\static\agent\updater.ps1" >nul
if errorlevel 1 exit /b 1
copy /y "runner.ps1" "..\server\static\agent\runner.ps1" >nul
if errorlevel 1 exit /b 1

echo.
echo Build succeeded.
exit /b 0
