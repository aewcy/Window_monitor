# Monitor Agent - Windows 服务安装器
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$ErrorActionPreference = "Stop"

$script:ServiceName = "MonitorAgent"
$script:DisplayName = "Monitor Agent"
$script:InstallDir = Join-Path $env:ProgramFiles "MonitorAgent"
$script:InstallExe = Join-Path $script:InstallDir "monitor-agent.exe"
$script:SourceExe = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "monitor-agent.exe"
$script:OldTaskName = "MonitorAgent"

if (-not (Test-Path $script:SourceExe)) {
    [System.Windows.Forms.MessageBox]::Show("未找到 monitor-agent.exe，请把安装脚本和程序放在同一个文件夹。", "安装失败", "OK", "Error") | Out-Null
    exit 1
}

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Start-Process powershell.exe -ArgumentList "-ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

function Invoke-Sc {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)
    $output = & sc.exe @Args 2>&1
    return @{
        Code = $LASTEXITCODE
        Text = ($output | Out-String).Trim()
    }
}

function Get-AgentService {
    Get-Service -Name $script:ServiceName -ErrorAction SilentlyContinue
}

function Update-Status {
    $svc = Get-AgentService
    if ($svc) {
        $lbl.Text = "状态：已安装 / $($svc.Status)"
        $bInstall.Enabled = $false
        $bRemove.Enabled = $true
        $bStart.Enabled = $svc.Status -ne "Running"
        $bStop.Enabled = $svc.Status -eq "Running"
    } else {
        $lbl.Text = "状态：未安装"
        $bInstall.Enabled = $true
        $bRemove.Enabled = $false
        $bStart.Enabled = $false
        $bStop.Enabled = $false
    }
}

function Remove-OldTask {
    & schtasks.exe /End /TN $script:OldTaskName 2>&1 | Out-Null
    & schtasks.exe /Delete /TN $script:OldTaskName /F 2>&1 | Out-Null
}

function Install-AgentService {
    New-Item -ItemType Directory -Force -Path $script:InstallDir | Out-Null
    Copy-Item -Force -Path $script:SourceExe -Destination $script:InstallExe

    Remove-OldTask

    $existing = Get-AgentService
    if ($existing) {
        if ($existing.Status -eq "Running") {
            Stop-Service -Name $script:ServiceName -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 2
        }
        $deleteResult = Invoke-Sc delete $script:ServiceName
        if ($deleteResult.Code -ne 0) {
            throw "删除旧服务失败：$($deleteResult.Text)"
        }
        Start-Sleep -Seconds 2
    }

    $binPath = "`"$script:InstallExe`" --service-run"
    $createResult = Invoke-Sc create $script:ServiceName binPath= $binPath start= auto DisplayName= $script:DisplayName
    if ($createResult.Code -ne 0) {
        throw "创建服务失败：$($createResult.Text)"
    }

    Invoke-Sc description $script:ServiceName "员工监控 Agent：截图采集、应用记录、浏览器历史上报。" | Out-Null
    Start-Service -Name $script:ServiceName
}

function Remove-AgentService {
    $svc = Get-AgentService
    if ($svc) {
        if ($svc.Status -eq "Running") {
            Stop-Service -Name $script:ServiceName -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 2
        }
        $deleteResult = Invoke-Sc delete $script:ServiceName
        if ($deleteResult.Code -ne 0) {
            throw "卸载服务失败：$($deleteResult.Text)"
        }
    }
    Remove-OldTask
}

$form = New-Object System.Windows.Forms.Form
$form.Text = "Monitor Agent 服务安装器"
$form.Size = New-Object System.Drawing.Size(430, 220)
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.BackColor = [System.Drawing.Color]::FromArgb(30, 30, 35)
$form.ForeColor = [System.Drawing.Color]::White

$title = New-Object System.Windows.Forms.Label
$title.Text = "Monitor Agent"
$title.Font = New-Object System.Drawing.Font("Microsoft YaHei UI", 15, [System.Drawing.FontStyle]::Bold)
$title.ForeColor = [System.Drawing.Color]::FromArgb(100, 200, 255)
$title.AutoSize = $true
$title.Location = New-Object System.Drawing.Point(22, 16)
$form.Controls.Add($title)

$lbl = New-Object System.Windows.Forms.Label
$lbl.Font = New-Object System.Drawing.Font("Microsoft YaHei UI", 9)
$lbl.ForeColor = [System.Drawing.Color]::FromArgb(210, 210, 210)
$lbl.Size = New-Object System.Drawing.Size(370, 26)
$lbl.Location = New-Object System.Drawing.Point(22, 55)
$form.Controls.Add($lbl)

function New-Btn($text, $x, $width, $color) {
    $btn = New-Object System.Windows.Forms.Button
    $btn.Text = $text
    $btn.Font = New-Object System.Drawing.Font("Microsoft YaHei UI", 9, [System.Drawing.FontStyle]::Bold)
    $btn.Size = New-Object System.Drawing.Size($width, 32)
    $btn.Location = New-Object System.Drawing.Point($x, 96)
    $btn.FlatStyle = "Flat"
    $btn.BackColor = $color
    $btn.ForeColor = [System.Drawing.Color]::White
    $btn.FlatAppearance.BorderSize = 0
    return $btn
}

$bInstall = New-Btn "安装服务" 22 84 ([System.Drawing.Color]::FromArgb(46, 139, 87))
$bRemove = New-Btn "卸载" 116 64 ([System.Drawing.Color]::FromArgb(178, 34, 34))
$bStart = New-Btn "启动" 190 64 ([System.Drawing.Color]::FromArgb(30, 100, 180))
$bStop = New-Btn "停止" 264 64 ([System.Drawing.Color]::FromArgb(120, 80, 30))
$bRefresh = New-Btn "刷新" 338 54 ([System.Drawing.Color]::FromArgb(80, 80, 80))
$form.Controls.AddRange(@($bInstall, $bRemove, $bStart, $bStop, $bRefresh))

$hint = New-Object System.Windows.Forms.Label
$hint.Text = "安装位置：$script:InstallDir"
$hint.Font = New-Object System.Drawing.Font("Microsoft YaHei UI", 8)
$hint.ForeColor = [System.Drawing.Color]::FromArgb(120, 120, 120)
$hint.AutoSize = $true
$hint.Location = New-Object System.Drawing.Point(22, 150)
$form.Controls.Add($hint)

$bInstall.Add_Click({
    try {
        Install-AgentService
        [System.Windows.Forms.MessageBox]::Show("安装成功，服务已启动。", "完成", "OK", "Information") | Out-Null
    } catch {
        [System.Windows.Forms.MessageBox]::Show("安装失败：$($_.Exception.Message)", "错误", "OK", "Error") | Out-Null
    }
    Update-Status
})

$bRemove.Add_Click({
    $confirm = [System.Windows.Forms.MessageBox]::Show("确定卸载 Monitor Agent 服务？", "确认", "YesNo", "Question")
    if ($confirm -eq "Yes") {
        try {
            Remove-AgentService
            [System.Windows.Forms.MessageBox]::Show("已卸载。", "完成", "OK", "Information") | Out-Null
        } catch {
            [System.Windows.Forms.MessageBox]::Show("卸载失败：$($_.Exception.Message)", "错误", "OK", "Error") | Out-Null
        }
        Update-Status
    }
})

$bStart.Add_Click({
    try { Start-Service -Name $script:ServiceName } catch {
        [System.Windows.Forms.MessageBox]::Show("启动失败：$($_.Exception.Message)", "错误", "OK", "Error") | Out-Null
    }
    Start-Sleep -Milliseconds 500
    Update-Status
})

$bStop.Add_Click({
    try { Stop-Service -Name $script:ServiceName -Force } catch {
        [System.Windows.Forms.MessageBox]::Show("停止失败：$($_.Exception.Message)", "错误", "OK", "Error") | Out-Null
    }
    Start-Sleep -Milliseconds 500
    Update-Status
})

$bRefresh.Add_Click({ Update-Status })

Update-Status
[void]$form.ShowDialog()
