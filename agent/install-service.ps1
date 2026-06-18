# Monitor Agent - Service Installer GUI (Non-blocking)

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$script:ServiceName = "MonitorAgent"
$script:DisplayName = "Monitor Agent"
$script:ExePath = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "monitor-agent.exe"

# Check exe
if (-not (Test-Path $script:ExePath)) {
    [System.Windows.Forms.MessageBox]::Show("monitor-agent.exe not found in same folder", "Error", "OK", "Error")
    exit 1
}

# Check admin
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Start-Process powershell.exe -ArgumentList "-ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

# Build GUI
$form = New-Object System.Windows.Forms.Form
$form.Text = "Monitor Agent Installer"
$form.Size = New-Object System.Drawing.Size(400, 260)
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

$lbl = New-Object System.Windows.Forms.Label
$lbl.Font = New-Object System.Drawing.Font("Segoe UI", 10)
$lbl.ForeColor = [System.Drawing.Color]::FromArgb(180, 180, 180)
$lbl.Size = New-Object System.Drawing.Size(350, 40)
$lbl.Location = New-Object System.Drawing.Point(20, 55)
$form.Controls.Add($lbl)

$lbl2 = New-Object System.Windows.Forms.Label
$lbl2.Text = "Host: $env:COMPUTERNAME"
$lbl2.Font = New-Object System.Drawing.Font("Segoe UI", 8)
$lbl2.ForeColor = [System.Drawing.Color]::FromArgb(100, 100, 100)
$lbl2.AutoSize = $true
$lbl2.Location = New-Object System.Drawing.Point(20, 195)
$form.Controls.Add($lbl2)

function New-Btn($t, $x, $w, $c) {
    $b = New-Object System.Windows.Forms.Button
    $b.Text = $t; $b.Font = New-Object System.Drawing.Font("Segoe UI", 10, [System.Drawing.FontStyle]::Bold)
    $b.Size = New-Object System.Drawing.Size($w, 36); $b.Location = New-Object System.Drawing.Point($x, 110)
    $b.FlatStyle = "Flat"; $b.BackColor = $c; $b.ForeColor = [System.Drawing.Color]::White
    $b.FlatAppearance.BorderSize = 0; $b.Cursor = [System.Windows.Forms.Cursors]::Hand
    return $b
}

$b1 = New-Btn "Install" 20 80 ([System.Drawing.Color]::FromArgb(46, 139, 87))
$b2 = New-Btn "Uninstall" 110 80 ([System.Drawing.Color]::FromArgb(178, 34, 34))
$b3 = New-Btn "Start" 200 80 ([System.Drawing.Color]::FromArgb(30, 100, 180))
$b4 = New-Btn "Stop" 290 70 ([System.Drawing.Color]::FromArgb(120, 80, 30))
$form.Controls.AddRange(@($b1, $b2, $b3, $b4))

# Status refresh timer (non-blocking)
$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 2000
$timer.Add_Tick({
    $svc = Get-Service -Name $script:ServiceName -ErrorAction SilentlyContinue
    if ($svc) {
        $lbl.Text = "Status: $($svc.Status)  |  StartType: $($svc.StartType)"
        $b1.Enabled = $false; $b2.Enabled = $true
        $b3.Enabled = ($svc.Status -ne "Running"); $b4.Enabled = ($svc.Status -eq "Running")
    } else {
        $lbl.Text = "Not Installed"; $b1.Enabled = $true; $b2.Enabled = $false; $b3.Enabled = $false; $b4.Enabled = $false
    }
})
$timer.Start()

# All actions run in background (non-blocking)
$b1.Add_Click({
    $lbl.Text = "Installing..."
    Start-Job -ScriptBlock {
        param($name, $display, $exe)
        New-Service -Name $name -BinaryPathName $exe -DisplayName $display -StartupType Automatic
    } -ArgumentList $script:ServiceName, $script:DisplayName, $script:ExePath | Out-Null
})

$b2.Add_Click({
    $r = [System.Windows.Forms.MessageBox]::Show("Uninstall service?", "Confirm", "YesNo", "Question")
    if ($r -eq "Yes") {
        $lbl.Text = "Uninstalling..."
        Start-Job -ScriptBlock {
            param($name)
            Stop-Service -Name $name -Force -ErrorAction SilentlyContinue
            sc.exe delete $name | Out-Null
        } -ArgumentList $script:ServiceName | Out-Null
    }
})

$b3.Add_Click({
    $lbl.Text = "Starting..."
    Start-Job -ScriptBlock { param($name) sc.exe start $name | Out-Null } -ArgumentList $script:ServiceName | Out-Null
})

$b4.Add_Click({
    $lbl.Text = "Stopping..."
    Start-Job -ScriptBlock { param($name) sc.exe stop $name | Out-Null } -ArgumentList $script:ServiceName | Out-Null
})

# Initial status
$svc = Get-Service -Name $script:ServiceName -ErrorAction SilentlyContinue
if ($svc) { $lbl.Text = "Status: $($svc.Status)  |  StartType: $($svc.StartType)" }
else { $lbl.Text = "Not Installed" }

[void]$form.ShowDialog()
$timer.Stop()
$timer.Dispose()
