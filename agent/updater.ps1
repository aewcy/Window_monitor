param(
    [Parameter(Mandatory=$true)][string]$InstallDir,
    [Parameter(Mandatory=$true)][string]$NewExe,
    [Parameter(Mandatory=$true)][string]$TargetVersion
)

$ErrorActionPreference = "Stop"

$ProcessName = "WindowsMonitor"
$MainTaskName = "Windows Monitor"
$ExePath = Join-Path $InstallDir "$ProcessName.exe"
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

function Stop-Agent {
    schtasks.exe /End /TN $MainTaskName 2>$null | Out-Null
    Get-Process -Name $ProcessName -ErrorAction SilentlyContinue | ForEach-Object {
        try {
            Write-UpdateLog "停止旧进程 PID=$($_.Id)"
            Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
        } catch {
            Write-UpdateLog "停止旧进程失败 PID=$($_.Id): $($_.Exception.Message)"
        }
    }
    Start-Sleep -Seconds 2
}

function Start-Agent {
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
    Write-UpdateState "installing" "开始安装更新"
    Write-UpdateLog "开始更新到 $TargetVersion"

    if (-not (Test-Path $NewExe)) {
        throw "新版本文件不存在: $NewExe"
    }
    if (-not (Test-Path $ExePath)) {
        throw "当前 Agent 文件不存在: $ExePath"
    }

    New-Item -ItemType Directory -Force -Path $PreviousDir | Out-Null
    $backupPath = Join-Path $PreviousDir ("{0}-{1}.exe" -f $ProcessName, (Get-Date -Format "yyyyMMddHHmmss"))

    Stop-Agent
    Copy-Item -Force -Path $ExePath -Destination $backupPath
    Copy-Item -Force -Path $NewExe -Destination $ExePath

    Write-UpdateState "updated" "文件替换完成，正在启动新版本"
    Write-UpdateLog "文件替换完成，备份: $backupPath"
    Start-Agent
    Write-UpdateLog "启动命令已执行"
    exit 0
} catch {
    $message = $_.Exception.Message
    Write-UpdateLog "更新失败: $message"
    try {
        if ($backupPath -and (Test-Path $backupPath)) {
            Copy-Item -Force -Path $backupPath -Destination $ExePath
            Write-UpdateState "rolled_back" "更新失败，已回滚: $message"
            Write-UpdateLog "已回滚到 $backupPath"
            Start-Agent
        } else {
            Write-UpdateState "failed" $message
            Start-Agent
        }
    } catch {
        Write-UpdateLog "回滚失败: $($_.Exception.Message)"
        Write-UpdateState "failed" "更新失败且回滚失败: $message"
    }
    exit 1
}
