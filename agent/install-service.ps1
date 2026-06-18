# Monitor Agent - One-click Service Installer GUI

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$ServiceName = "MonitorAgent"
$DisplayName = "Monitor Agent"
$ExeName = "monitor-agent.exe"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ExePath = Join-Path $ScriptDir $ExeName

if (-not (Test-Path $ExePath)) {
    [System.Windows.Forms.MessageBox]::Show("Cannot find $ExeName in $ScriptDir", "Error", "OK", "Error")
    exit 1
}

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Start-Process powershell.exe -ArgumentList "-ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

$form = New-Object System.Windows.Forms.Form
$form.Text = "Monitor Agent Installer"
$form.Size = New-Object System.Drawing.Size(420, 300)
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.BackColor = [System.Drawing.Color]::FromArgb(30, 30, 35)
$form.ForeColor = [System.Drawing.Color]::White

$title = New-Object System.Windows.Forms.Label
$title.Text = "Monitor Agent"
$title.Font = New-Object System.Drawing.Font("Segoe UI", 16, [System.Drawing.FontStyle]::Bold)
$title.ForeColor = [System.Drawing.Color]::FromArgb(100, 200, 255)
$title.AutoSize = $true
$title.Location = New-Object System.Drawing.Point(20, 15)
$form.Controls.Add($title)

$statusLabel = New-Object System.Windows.Forms.Label
$statusLabel.Font = New-Object System.Drawing.Font("Segoe UI", 10)
$statusLabel.ForeColor = [System.Drawing.Color]::FromArgb(180, 180, 180)
$statusLabel.Size = New-Object System.Drawing.Size(370, 50)
$statusLabel.Location = New-Object System.Drawing.Point(20, 55)
$form.Controls.Add($statusLabel)

$infoLabel = New-Object System.Windows.Forms.Label
$infoLabel.Text = "Host: $env:COMPUTERNAME | Path: $ExePath"
$infoLabel.Font = New-Object System.Drawing.Font("Segoe UI", 8)
$infoLabel.ForeColor = [System.Drawing.Color]::FromArgb(100, 100, 100)
$infoLabel.Size = New-Object System.Drawing.Size(370, 20)
$infoLabel.Location = New-Object System.Drawing.Point(20, 230)
$form.Controls.Add($infoLabel)

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

function Refresh-Status {
    $svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($svc) {
        $statusLabel.Text = "Status: $($svc.Status) | StartType: $($svc.StartType)"
        $installBtn.Enabled = $false
        $uninstallBtn.Enabled = $true
        $startBtn.Enabled = ($svc.Status -ne "Running")
        $stopBtn.Enabled = ($svc.Status -eq "Running")
    } else {
        $statusLabel.Text = "Not Installed"
        $installBtn.Enabled = $true
        $uninstallBtn.Enabled = $false
        $startBtn.Enabled = $false
        $stopBtn.Enabled = $false
    }
}

$installBtn = New-Button "Install" 20 120 90 40 ([System.Drawing.Color]::FromArgb(46, 139, 87))
$uninstallBtn = New-Button "Uninstall" 120 120 90 40 ([System.Drawing.Color]::FromArgb(178, 34, 34))
$startBtn = New-Button "Start" 220 120 90 40 ([System.Drawing.Color]::FromArgb(30, 100, 180))
$stopBtn = New-Button "Stop" 320 120 70 40 ([System.Drawing.Color]::FromArgb(120, 80, 30))

$form.Controls.AddRange(@($installBtn, $uninstallBtn, $startBtn, $stopBtn))

$installBtn.Add_Click({
    try {
        New-Service -Name $ServiceName -BinaryPathName $ExePath -DisplayName $DisplayName -Description "Monitor Agent - Screenshot, Activity, Browser History" -StartupType Automatic
        [System.Windows.Forms.MessageBox]::Show("Install OK!`n`nService: $DisplayName`nStartType: Automatic (boot on startup)", "Success", "OK", "Information")
        Refresh-Status
    } catch {
        [System.Windows.Forms.MessageBox]::Show("Install failed: $_", "Error", "OK", "Error")
    }
})

$uninstallBtn.Add_Click({
    $result = [System.Windows.Forms.MessageBox]::Show("Uninstall Monitor Agent service?", "Confirm", "YesNo", "Question")
    if ($result -eq "Yes") {
        try {
            Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
            sc.exe delete $ServiceName | Out-Null
            [System.Windows.Forms.MessageBox]::Show("Uninstalled", "Success", "OK", "Information")
            Refresh-Status
        } catch {
            [System.Windows.Forms.MessageBox]::Show("Uninstall failed: $_", "Error", "OK", "Error")
        }
    }
})

$startBtn.Add_Click({
    try {
        Start-Service -Name $ServiceName
        Start-Sleep -Seconds 1
        Refresh-Status
    } catch {
        [System.Windows.Forms.MessageBox]::Show("Start failed: $_", "Error", "OK", "Error")
    }
})

$stopBtn.Add_Click({
    try {
        Stop-Service -Name $ServiceName -Force
        Start-Sleep -Seconds 1
        Refresh-Status
    } catch {
        [System.Windows.Forms.MessageBox]::Show("Stop failed: $_", "Error", "OK", "Error")
    }
})

Refresh-Status
[void]$form.ShowDialog()
