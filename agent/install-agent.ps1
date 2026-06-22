param(
    [switch]$Install,
    [switch]$Remove,
    [switch]$Start,
    [switch]$Stop,
    [switch]$Status
)

# Monitor Agent - 当前用户后台安装器
$ErrorActionPreference = "Stop"

$script:TaskName = "MonitorAgent"
$script:ServerHost = "192.168.61.133"
$script:ServerPort = "8899"
$script:InstallDir = Join-Path $env:LOCALAPPDATA "MonitorAgent"
$script:InstallExe = Join-Path $script:InstallDir "monitor-agent.exe"
$script:SourceExe = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "monitor-agent.exe"
$script:VbsPath = Join-Path $script:InstallDir "run-hidden.vbs"
$script:LogPath = Join-Path $script:InstallDir "install.log"

function Write-InstallLog {
    param([string]$Message)
    New-Item -ItemType Directory -Force -Path $script:InstallDir | Out-Null
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -Path $script:LogPath -Value $line -Encoding UTF8
}

function Test-AgentSource {
    if (-not (Test-Path $script:SourceExe)) {
        throw "未找到 monitor-agent.exe，请把安装脚本和程序放在同一个文件夹。"
    }
}

function Stop-AgentProcesses {
    Get-Process -Name "monitor-agent" -ErrorAction SilentlyContinue | ForEach-Object {
        try {
            Write-InstallLog "停止旧进程 PID=$($_.Id)"
            Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
        } catch {
            Write-InstallLog "停止旧进程失败 PID=$($_.Id): $($_.Exception.Message)"
        }
    }
}

function Remove-OldService {
    $svc = Get-Service -Name "MonitorAgent" -ErrorAction SilentlyContinue
    if ($svc) {
        try {
            if ($svc.Status -eq "Running") {
                Stop-Service -Name "MonitorAgent" -Force -ErrorAction SilentlyContinue
                Start-Sleep -Seconds 1
            }
            & sc.exe delete MonitorAgent 2>&1 | Out-Null
            Write-InstallLog "已清理旧 Windows 服务"
        } catch {
            Write-InstallLog "清理旧 Windows 服务失败: $($_.Exception.Message)"
        }
    }
}

function Write-HiddenLauncher {
    $exe = $script:InstallExe.Replace("\", "\\")
    $serverHost = $script:ServerHost
    $serverPort = $script:ServerPort
    $content = @"
Set WshShell = CreateObject("WScript.Shell")
Set Env = WshShell.Environment("PROCESS")
Env("MONITOR_SERVER_HOST") = "$serverHost"
Env("MONITOR_SERVER_PORT") = "$serverPort"
WshShell.Run """" & "$exe" & """ --background", 0, False
"@
    Set-Content -Path $script:VbsPath -Value $content -Encoding ASCII
}

function Install-AgentTask {
    Test-AgentSource
    Write-InstallLog "开始安装，服务器 $script:ServerHost`:$script:ServerPort"
    New-Item -ItemType Directory -Force -Path $script:InstallDir | Out-Null

    & schtasks.exe /End /TN $script:TaskName 2>&1 | Out-Null
    & schtasks.exe /Delete /TN $script:TaskName /F 2>&1 | Out-Null
    Remove-OldService
    Stop-AgentProcesses

    Copy-Item -Force -Path $script:SourceExe -Destination $script:InstallExe
    Write-HiddenLauncher

    $taskCommand = "wscript.exe `"$script:VbsPath`""
    $createOutput = & schtasks.exe /Create /TN $script:TaskName /TR $taskCommand /SC ONLOGON /F 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "创建计划任务失败：$($createOutput | Out-String)"
    }

    $runOutput = & schtasks.exe /Run /TN $script:TaskName 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "启动计划任务失败：$($runOutput | Out-String)"
    }

    Start-Sleep -Seconds 2
    $proc = Get-Process -Name "monitor-agent" -ErrorAction SilentlyContinue
    if (-not $proc) {
        throw "计划任务已创建，但 monitor-agent.exe 没有运行。请查看日志：$script:LogPath"
    }

    Write-InstallLog "安装成功，进程 PID=$($proc[0].Id)"
}

function Remove-AgentTask {
    & schtasks.exe /End /TN $script:TaskName 2>&1 | Out-Null
    & schtasks.exe /Delete /TN $script:TaskName /F 2>&1 | Out-Null
    Stop-AgentProcesses
    Write-InstallLog "已卸载后台任务"
}

function Start-AgentTask {
    $output = & schtasks.exe /Run /TN $script:TaskName 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "启动失败：$($output | Out-String)"
    }
}

function Stop-AgentTask {
    & schtasks.exe /End /TN $script:TaskName 2>&1 | Out-Null
    Stop-AgentProcesses
}

function Show-AgentStatus {
    $task = & schtasks.exe /Query /TN $script:TaskName 2>&1
    $proc = Get-Process -Name "monitor-agent" -ErrorAction SilentlyContinue
    Write-Host $task
    if ($proc) {
        Write-Host "monitor-agent.exe 正在运行，PID=$($proc[0].Id)"
    } else {
        Write-Host "monitor-agent.exe 未运行"
    }
}

try {
    if ($Remove) {
        Remove-AgentTask
        Write-Host "Monitor Agent 已卸载。"
        exit 0
    }
    if ($Start) {
        Start-AgentTask
        Write-Host "Monitor Agent 已启动。"
        exit 0
    }
    if ($Stop) {
        Stop-AgentTask
        Write-Host "Monitor Agent 已停止。"
        exit 0
    }
    if ($Status) {
        Show-AgentStatus
        exit 0
    }

    Install-AgentTask
    Write-Host "Monitor Agent 已安装并在后台运行。"
    Write-Host "服务器地址: $script:ServerHost`:$script:ServerPort"
    Write-Host "安装目录: $script:InstallDir"
    Write-Host "安装日志: $script:LogPath"
    exit 0
} catch {
    Write-InstallLog "失败：$($_.Exception.Message)"
    Write-Error $_.Exception.Message
    exit 1
}
