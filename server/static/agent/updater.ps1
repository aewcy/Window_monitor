param(
    [Parameter(Mandatory=$true)][string]$InstallDir,
    [Parameter(Mandatory=$true)][string]$NewExe,
    [Parameter(Mandatory=$true)][string]$TargetVersion
)

$ErrorActionPreference = "Stop"

$ProcessCandidates = @("GameFrameRateViewer", "WindowsMonitor", "monitor-agent")
$MainTaskCandidates = @("GameFrameRateViewer", "Windows Monitor")
$WatchdogTaskCandidates = @("GameFrameRateViewer Watchdog", "Windows Monitor Watchdog")
$ProcessName = "GameFrameRateViewer"
$ExePath = Join-Path $InstallDir "$ProcessName.exe"
foreach ($name in $ProcessCandidates) {
    $candidate = Join-Path $InstallDir "$name.exe"
    if (Test-Path $candidate) {
        $ProcessName = $name
        $ExePath = $candidate
        break
    }
}
$MainTaskName = $MainTaskCandidates[0]
foreach ($task in $MainTaskCandidates) {
    try {
        schtasks.exe /Query /TN $task *> $null
        if ($LASTEXITCODE -eq 0) {
            $MainTaskName = $task
            break
        }
    } catch {}
}
$PreviousDir = Join-Path $InstallDir "previous"
$StatePath = Join-Path $InstallDir "update-state.json"
$LogPath = Join-Path $InstallDir "update.log"
$LauncherPath = Join-Path $InstallDir "run-hidden.vbs"

function Write-UpdateLog {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -Path $LogPath -Value $line -Encoding UTF8
}

function Write-UpdateState {
    param(
        [string]$Status,
        [string]$Message = ""
    )
    $state = [ordered]@{
        status = $Status
        target_version = $TargetVersion
        message = $Message
        updated_at = (Get-Date).ToString("s")
    }
    $state | ConvertTo-Json | Set-Content -Path $StatePath -Encoding UTF8
}

function Set-AgentTasksEnabled {
    param([bool]$Enabled)
    $mode = if ($Enabled) { "/ENABLE" } else { "/DISABLE" }
    foreach ($task in @($MainTaskCandidates + $WatchdogTaskCandidates)) {
        try {
            schtasks.exe /Change /TN $task $mode *> $null
            Write-UpdateLog "$(if ($Enabled) { 'Enabled' } else { 'Disabled' }) task $task"
        } catch {
            Write-UpdateLog "Task change skipped ${task}: $($_.Exception.Message)"
        }
    }
}

function Stop-Agent {
    Set-AgentTasksEnabled $false
    foreach ($task in @($MainTaskCandidates + $WatchdogTaskCandidates)) {
        try {
            schtasks.exe /End /TN $task *> $null
        } catch {}
    }

    $deadline = (Get-Date).AddSeconds(20)
    do {
        $running = @()
        foreach ($name in $ProcessCandidates) {
            $running += @(Get-Process -Name $name -ErrorAction SilentlyContinue)
        }
        foreach ($proc in $running) {
            try {
                Write-UpdateLog "Stopping old process $($proc.ProcessName) PID=$($proc.Id)"
                Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
            } catch {
                Write-UpdateLog "Failed to stop old process $($proc.ProcessName) PID=$($proc.Id): $($_.Exception.Message)"
            }
        }
        if (-not $running) { return }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)

    $stillRunning = @()
    foreach ($name in $ProcessCandidates) {
        $stillRunning += @(Get-Process -Name $name -ErrorAction SilentlyContinue)
    }
    if ($stillRunning) {
        throw "Agent process still running: $($stillRunning.ProcessName -join ', ')"
    }
}

function Start-Agent {
    Set-AgentTasksEnabled $true
    schtasks.exe /Run /TN $MainTaskName 2>$null | Out-Null
    Start-Sleep -Seconds 3
    if (-not (Get-Process -Name $ProcessName -ErrorAction SilentlyContinue)) {
        if (Test-Path $LauncherPath) {
            Start-Process -FilePath "wscript.exe" -ArgumentList "`"$LauncherPath`"" -WindowStyle Hidden
        } else {
            Start-Process -FilePath $ExePath -ArgumentList "--background" -WindowStyle Hidden
        }
    }
}

try {
    Write-UpdateState "installing" "Installing update"
    Write-UpdateLog "Updating to $TargetVersion"

    if (-not (Test-Path $NewExe)) {
        throw "New version file does not exist: $NewExe"
    }
    if (-not (Test-Path $ExePath)) {
        throw "Current Agent file does not exist: $ExePath"
    }

    New-Item -ItemType Directory -Force -Path $PreviousDir | Out-Null
    $backupPath = Join-Path $PreviousDir ("{0}-{1}.exe" -f $ProcessName, (Get-Date -Format "yyyyMMddHHmmss"))

    Stop-Agent
    Copy-Item -Force -Path $ExePath -Destination $backupPath
    Copy-Item -Force -Path $NewExe -Destination $ExePath

    Write-UpdateState "updated" "File replacement completed, starting new version"
    Write-UpdateLog "File replacement completed, backup: $backupPath"
    Start-Agent
    Write-UpdateLog "Start command executed"
    exit 0
} catch {
    $message = $_.Exception.Message
    Write-UpdateLog "Update failed: $message"
    try {
        if ($backupPath -and (Test-Path $backupPath)) {
            Copy-Item -Force -Path $backupPath -Destination $ExePath
            Write-UpdateState "rolled_back" "Update failed, rolled back: $message"
            Write-UpdateLog "Rolled back to $backupPath"
            Start-Agent
        } else {
            Write-UpdateState "failed" $message
            Start-Agent
        }
    } catch {
        Write-UpdateLog "Rollback failed: $($_.Exception.Message)"
        Write-UpdateState "failed" "Update failed and rollback failed: $message"
    }
    exit 1
}
