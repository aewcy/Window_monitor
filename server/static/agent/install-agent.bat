@echo off
setlocal
cd /d "%~dp0"

if not exist "monitor-agent.exe" (
    echo monitor-agent.exe was not found.
    echo Please extract the full MonitorAgent.zip before running install-agent.bat.
    pause
    exit /b 1
)

echo.
echo Requesting administrator permission and installing GameFrameRateViewer...
echo If a Windows permission prompt appears, click Yes.
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$script = Join-Path '%~dp0' 'install-agent.ps1'; $args = @('-NoProfile','-ExecutionPolicy','Bypass','-File', ('\"' + $script + '\"'), '-Install'); $p = Start-Process -FilePath 'powershell.exe' -ArgumentList $args -Verb RunAs -Wait -PassThru; exit $p.ExitCode"
if errorlevel 1 (
    echo.
    echo Install failed. Check the log:
    echo %LOCALAPPDATA%\GameFrameRateViewer\logs\install.log
    pause
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$taskOk = (schtasks.exe /Query /TN 'GameFrameRateViewer' 2>$null) -ne $null; $procOk = (Get-Process -Name 'GameFrameRateViewer' -ErrorAction SilentlyContinue) -ne $null; if (-not $taskOk -or -not $procOk) { exit 2 }"
if errorlevel 1 (
    echo.
    echo Installer returned, but the background process or scheduled task was not detected.
    echo Check the log:
    echo %LOCALAPPDATA%\GameFrameRateViewer\logs\install.log
    echo You can also right-click install-agent.bat and choose Run as administrator.
    pause
    exit /b 1
)

echo.
echo GameFrameRateViewer has been installed and started in the background.
echo Search for GameFrameRateViewer in Task Manager.
pause
