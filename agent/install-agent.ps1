param(
    [switch]$Install,
    [switch]$Remove,
    [switch]$Start,
    [switch]$Stop,
    [switch]$Status
)

$ErrorActionPreference = "Stop"

$script:ProductName = "Windows Monitor"
$script:ProcessName = "WindowsMonitor"
$script:MainTaskName = "Windows Monitor"
$script:WatchdogTaskName = "Windows Monitor Watchdog"
$script:ServerHost = "192.168.61.133"
$script:ServerPort = "8899"
$script:InstallDir = Join-Path $env:ProgramData "Windows Monitor"
$script:UserDataDir = Join-Path $env:LOCALAPPDATA "Windows Monitor"
$script:InstallExe = Join-Path $script:InstallDir "$script:ProcessName.exe"
$script:SourceExe = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "monitor-agent.exe"
$script:LauncherPath = Join-Path $script:InstallDir "run-hidden.vbs"
$script:WatchdogPath = Join-Path $script:InstallDir "watchdog.ps1"
$script:ConfigPath = Join-Path $script:InstallDir "config.json"
$script:LogDir = Join-Path $script:UserDataDir "logs"
$script:LogPath = Join-Path $script:LogDir "install.log"

function Write-InstallLog {
    param([string]$Message)
    New-Item -ItemType Directory -Force -Path $script:LogDir | Out-Null
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -Path $script:LogPath -Value $line -Encoding UTF8
}

function Assert-Admin {
    $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if ($isAdmin) { return }

    $argList = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$PSCommandPath`"")
    if ($Install) { $argList += "-Install" }
    if ($Remove) { $argList += "-Remove" }
    if ($Start) { $argList += "-Start" }
    if ($Stop) { $argList += "-Stop" }
    if ($Status) { $argList += "-Status" }
    Start-Process powershell.exe -ArgumentList ($argList -join " ") -Verb RunAs
    exit
}

function Test-AgentSource {
    if (-not (Test-Path $script:SourceExe)) {
        throw "未找到 monitor-agent.exe，请把安装脚本和程序放在同一个文件夹。"
    }
}

function Stop-AgentProcesses {
    foreach ($name in @($script:ProcessName, "monitor-agent")) {
        Get-Process -Name $name -ErrorAction SilentlyContinue | ForEach-Object {
            try {
                Write-InstallLog "停止旧进程 $name PID=$($_.Id)"
                Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
            } catch {
                Write-InstallLog "停止旧进程失败 $name PID=$($_.Id): $($_.Exception.Message)"
            }
        }
    }
}

function Remove-OldTasksAndService {
    foreach ($task in @($script:MainTaskName, $script:WatchdogTaskName, "MonitorAgent")) {
        & schtasks.exe /End /TN $task 2>&1 | Out-Null
        & schtasks.exe /Delete /TN $task /F 2>&1 | Out-Null
    }

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

function Set-InstallDirectoryAcl {
    $acl = Get-Acl $script:InstallDir
    $acl.SetAccessRuleProtection($true, $false)

    $rules = @(
        New-Object System.Security.AccessControl.FileSystemAccessRule("SYSTEM", "FullControl", "ContainerInherit,ObjectInherit", "None", "Allow"),
        New-Object System.Security.AccessControl.FileSystemAccessRule("Administrators", "FullControl", "ContainerInherit,ObjectInherit", "None", "Allow"),
        New-Object System.Security.AccessControl.FileSystemAccessRule("Users", "ReadAndExecute", "ContainerInherit,ObjectInherit", "None", "Allow")
    )
    foreach ($rule in $rules) {
        $acl.AddAccessRule($rule)
    }
    Set-Acl -Path $script:InstallDir -AclObject $acl
}

function Write-AgentConfig {
    $config = [ordered]@{
        server_host = $script:ServerHost
        server_port = $script:ServerPort
        install_dir = $script:InstallDir
        user_data_dir = $script:UserDataDir
        installed_at = (Get-Date).ToString("s")
    }
    $config | ConvertTo-Json | Set-Content -Path $script:ConfigPath -Encoding UTF8
}

function Write-HiddenLauncher {
    $exe = $script:InstallExe
    $serverHost = $script:ServerHost
    $serverPort = $script:ServerPort
    $content = @"
Set WshShell = CreateObject("WScript.Shell")
Set Env = WshShell.Environment("PROCESS")
Env("MONITOR_SERVER_HOST") = "$serverHost"
Env("MONITOR_SERVER_PORT") = "$serverPort"
WshShell.Run """" & "$exe" & """ --background", 0, False
"@
    Set-Content -Path $script:LauncherPath -Value $content -Encoding ASCII
}

function Write-WatchdogScript {
    $launcher = $script:LauncherPath.Replace("'", "''")
    $processName = $script:ProcessName
    $content = @"
`$proc = Get-Process -Name '$processName' -ErrorAction SilentlyContinue
if (-not `$proc) {
    Start-Process -FilePath 'wscript.exe' -ArgumentList '"$launcher"' -WindowStyle Hidden
}
"@
    Set-Content -Path $script:WatchdogPath -Value $content -Encoding UTF8
}

function New-MonitorTasks {
    $mainAction = "wscript.exe `"$script:LauncherPath`""
    $watchdogAction = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script:WatchdogPath`""

    $mainOut = & schtasks.exe /Create /TN $script:MainTaskName /TR $mainAction /SC ONLOGON /RL HIGHEST /F 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "创建登录启动任务失败：$($mainOut | Out-String)"
    }

    $watchOut = & schtasks.exe /Create /TN $script:WatchdogTaskName /TR $watchdogAction /SC MINUTE /MO 1 /RL HIGHEST /F 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "创建自恢复任务失败：$($watchOut | Out-String)"
    }
}

function Start-Monitor {
    & schtasks.exe /Run /TN $script:MainTaskName 2>&1 | Out-Null
    Start-Sleep -Seconds 2
    $proc = Get-Process -Name $script:ProcessName -ErrorAction SilentlyContinue
    if (-not $proc) {
        throw "$script:ProcessName.exe 没有运行。请查看日志：$script:LogPath"
    }
    Write-InstallLog "后台进程已启动 PID=$($proc[0].Id)"
}

function Install-Agent {
    Assert-Admin
    Test-AgentSource
    Write-InstallLog "开始安装 $script:ProductName，服务器 $script:ServerHost`:$script:ServerPort"

    New-Item -ItemType Directory -Force -Path $script:InstallDir | Out-Null
    New-Item -ItemType Directory -Force -Path $script:LogDir | Out-Null
    Remove-OldTasksAndService
    Stop-AgentProcesses

    Copy-Item -Force -Path $script:SourceExe -Destination $script:InstallExe
    Write-AgentConfig
    Write-HiddenLauncher
    Write-WatchdogScript
    Set-InstallDirectoryAcl
    New-MonitorTasks
    Start-Monitor

    Write-InstallLog "安装完成"
}

function Remove-Agent {
    Assert-Admin
    Remove-OldTasksAndService
    Stop-AgentProcesses
    if (Test-Path $script:InstallDir) {
        $acl = Get-Acl $script:InstallDir
        $acl.SetAccessRuleProtection($false, $true)
        Set-Acl -Path $script:InstallDir -AclObject $acl
        Remove-Item -LiteralPath $script:InstallDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    Write-InstallLog "卸载完成"
}

function Show-Status {
    $tasks = @($script:MainTaskName, $script:WatchdogTaskName)
    foreach ($task in $tasks) {
        & schtasks.exe /Query /TN $task 2>&1
    }
    $proc = Get-Process -Name $script:ProcessName -ErrorAction SilentlyContinue
    if ($proc) {
        Write-Host "$script:ProcessName.exe 正在运行，PID=$($proc[0].Id)"
    } else {
        Write-Host "$script:ProcessName.exe 未运行"
    }
}

try {
    if ($Remove) {
        Remove-Agent
        Write-Host "$script:ProductName 已卸载。"
        exit 0
    }
    if ($Stop) {
        Assert-Admin
        & schtasks.exe /End /TN $script:MainTaskName 2>&1 | Out-Null
        Stop-AgentProcesses
        Write-Host "$script:ProductName 已停止。"
        exit 0
    }
    if ($Start) {
        Assert-Admin
        Start-Monitor
        Write-Host "$script:ProductName 已启动。"
        exit 0
    }
    if ($Status) {
        Show-Status
        exit 0
    }

    Install-Agent
    Write-Host "$script:ProductName 已安装并在后台运行。"
    Write-Host "服务器地址: $script:ServerHost`:$script:ServerPort"
    Write-Host "安装目录: $script:InstallDir"
    Write-Host "日志目录: $script:LogDir"
    exit 0
} catch {
    Write-InstallLog "失败：$($_.Exception.Message)"
    Write-Error $_.Exception.Message
    exit 1
}
