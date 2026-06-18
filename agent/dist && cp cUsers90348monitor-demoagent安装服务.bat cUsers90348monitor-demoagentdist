# Monitor Agent — 一键安装 GUI
# 用法: 右键 → 使用 PowerShell 运行

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$ServiceName = "MonitorAgent"
$DisplayName = "Monitor Agent"
$ExeName = "monitor-agent.exe"

# 获取脚本所在目录（和 exe 同目录）
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ExePath = Join-Path $ScriptDir $ExeName

# ========== 检查 exe 是否存在 ==========
if (-not (Test-Path $ExePath)) {
    [System.Windows.Forms.MessageBox]::Show(
        "找不到 $ExeName`n请确保此脚本和 $ExeName 在同一目录。",
        "Monitor Agent 安装器",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error
    )
    exit 1
}

# ========== 检查管理员权限 ==========
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    # 自动以管理员身份重新启动
    Start-Process powershell.exe -ArgumentList "-ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

# ========== 创建 GUI ==========
$form = New-Object System.Windows.Forms.Form
$form.Text = "Monitor Agent 安装器"
$form.Size = New-Object System.Drawing.Size(420, 320)
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.BackColor = [System.Drawing.Color]::FromArgb(30, 30, 35)
$form.ForeColor = [System.Drawing.Color]::White

# 标题
$title = New-Object System.Windows.Forms.Label
$title.Text = "🖥 Monitor Agent"
$title.Font = New-Object System.Drawing.Font("Segoe UI", 16, [System.Drawing.FontStyle]::Bold)
$title.ForeColor = [System.Drawing.Color]::FromArgb(100, 200, 255)
$title.AutoSize = $true
$title.Location = New-Object System.Drawing.Point(20, 15)
$form.Controls.Add($title)

# 状态标签
$statusLabel = New-Object System.Windows.Forms.Label
$statusLabel.Font = New-Object System.Drawing.Font("Segoe UI", 10)
$statusLabel.ForeColor = [System.Drawing.Color]::FromArgb(180, 180, 180)
$statusLabel.Size = New-Object System.Drawing.Size(370, 60)
$statusLabel.Location = New-Object System.Drawing.Point(20, 55)
$form.Controls.Add($statusLabel)

# 信息标签
$infoLabel = New-Object System.Windows.Forms.Label
$infoLabel.Text = "主机名: $env:COMPUTERNAME`n路径: $ExePath"
$infoLabel.Font = New-Object System.Drawing.Font("Segoe UI", 9)
$infoLabel.ForeColor = [System.Drawing.Color]::FromArgb(120, 120, 120)
$infoLabel.Size = New-Object System.Drawing.Size(370, 40)
$infoLabel.Location = New-Object System.Drawing.Point(20, 220)
$form.Controls.Add($infoLabel)

# ========== 按钮样式函数 ==========
function New-Button($text, $x, $y, $w, $h, $color) {
    $btn = New-Object System.Windows.Forms.Button
    $btn.Text = $text
    $btn.Font = New-Object System.Drawing.Font("Segoe UI", 10, [System.Drawing.FontStyle]::Bold)
    $btn.Size = New-Object System.Drawing.Size($w, $h)
    $btn.Location = New-Object System.Drawing.Point($x, $y)
    $btn.FlatStyle = "Flat"
    $btn.BackColor = $color
    $btn.ForeColor = [System.Drawing.Color]::White
    $btn.FlatAppearance.BorderSize = 0
    $btn.Cursor = [System.Windows.Forms.Cursors]::Hand
    return $btn
}

# ========== 刷新状态 ==========
function Refresh-Status {
    $svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($svc) {
        $statusLabel.Text = "状态: $($svc.Status)`n启动类型: $($svc.StartType)"
        $installBtn.Enabled = $false
        $uninstallBtn.Enabled = $true
        $startBtn.Enabled = ($svc.Status -ne "Running")
        $stopBtn.Enabled = ($svc.Status -eq "Running")
    } else {
        $statusLabel.Text = "未安装"
        $installBtn.Enabled = $true
        $uninstallBtn.Enabled = $false
        $startBtn.Enabled = $false
        $stopBtn.Enabled = $false
    }
}

# ========== 按钮 ==========
$installBtn = New-Button "📦 安装" 20 130 90 40 ([System.Drawing.Color]::FromArgb(46, 139, 87))
$uninstallBtn = New-Button "🗑 卸载" 120 130 90 40 ([System.Drawing.Color]::FromArgb(178, 34, 34))
$startBtn = New-Button "▶ 启动" 220 130 90 40 ([System.Drawing.Color]::FromArgb(30, 100, 180))
$stopBtn = New-Button "⏹ 停止" 320 130 70 40 ([System.Drawing.Color]::FromArgb(120, 80, 30))

$form.Controls.AddRange(@($installBtn, $uninstallBtn, $startBtn, $stopBtn))

# ========== 安装 ==========
$installBtn.Add_Click({
    try {
        New-Service -Name $ServiceName -BinaryPathName $ExePath -DisplayName $DisplayName -Description "员工监控 Agent — 截图采集、活动记录、浏览器历史" -StartupType Automatic
        [System.Windows.Forms.MessageBox]::Show("安装成功！`n`n服务名称: $DisplayName`n启动类型: 自动（开机自启）", "成功", "OK", "Information")
        Refresh-Status
    } catch {
        [System.Windows.Forms.MessageBox]::Show("安装失败: $_", "错误", "OK", "Error")
    }
})

# ========== 卸载 ==========
$uninstallBtn.Add_Click({
    $result = [System.Windows.Forms.MessageBox]::Show("确定卸载 Monitor Agent 服务？", "确认", "YesNo", "Question")
    if ($result -eq "Yes") {
        try {
            Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
            sc.exe delete $ServiceName | Out-Null
            [System.Windows.Forms.MessageBox]::Show("已卸载", "成功", "OK", "Information")
            Refresh-Status
        } catch {
            [System.Windows.Forms.MessageBox]::Show("卸载失败: $_", "错误", "OK", "Error")
        }
    }
})

# ========== 启动 ==========
$startBtn.Add_Click({
    try {
        Start-Service -Name $ServiceName
        Start-Sleep -Seconds 1
        Refresh-Status
    } catch {
        [System.Windows.Forms.MessageBox]::Show("启动失败: $_", "错误", "OK", "Error")
    }
})

# ========== 停止 ==========
$stopBtn.Add_Click({
    try {
        Stop-Service -Name $ServiceName -Force
        Start-Sleep -Seconds 1
        Refresh-Status
    } catch {
        [System.Windows.Forms.MessageBox]::Show("停止失败: $_", "错误", "OK", "Error")
    }
})

# ========== 初始化 ==========
Refresh-Status
[void]$form.ShowDialog()
