# Monitor Agent - Installer GUI (Scheduled Task)
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$script:TaskName = "MonitorAgent"
$script:ExePath = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "monitor-agent.exe"

if (-not (Test-Path $script:ExePath)) {
    [System.Windows.Forms.MessageBox]::Show("monitor-agent.exe not found", "Error", "OK", "Error"); exit 1
}

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Start-Process powershell.exe -ArgumentList "-ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs; exit
}

$form = New-Object System.Windows.Forms.Form
$form.Text = "Monitor Agent"
$form.Size = New-Object System.Drawing.Size(380, 220)
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.BackColor = [System.Drawing.Color]::FromArgb(30, 30, 35)
$form.ForeColor = [System.Drawing.Color]::White

$title = New-Object System.Windows.Forms.Label
$title.Text = "Monitor Agent"
$title.Font = New-Object System.Drawing.Font("Segoe UI", 14, [System.Drawing.FontStyle]::Bold)
$title.ForeColor = [System.Drawing.Color]::FromArgb(100, 200, 255)
$title.AutoSize = $true
$title.Location = New-Object System.Drawing.Point(20, 12)
$form.Controls.Add($title)

$lbl = New-Object System.Windows.Forms.Label
$lbl.Font = New-Object System.Drawing.Font("Segoe UI", 9)
$lbl.ForeColor = [System.Drawing.Color]::FromArgb(180, 180, 180)
$lbl.Size = New-Object System.Drawing.Size(340, 30)
$lbl.Location = New-Object System.Drawing.Point(20, 45)
$form.Controls.Add($lbl)

function New-Btn($t, $x, $w, $c) {
    $b = New-Object System.Windows.Forms.Button
    $b.Text = $t; $b.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Bold)
    $b.Size = New-Object System.Drawing.Size($w, 32); $b.Location = New-Object System.Drawing.Point($x, 90)
    $b.FlatStyle = "Flat"; $b.BackColor = $c; $b.ForeColor = [System.Drawing.Color]::White
    $b.FlatAppearance.BorderSize = 0
    return $b
}

$b1 = New-Btn "Install" 20 70 ([System.Drawing.Color]::FromArgb(46, 139, 87))
$b2 = New-Btn "Remove" 100 70 ([System.Drawing.Color]::FromArgb(178, 34, 34))
$b3 = New-Btn "Start" 180 70 ([System.Drawing.Color]::FromArgb(30, 100, 180))
$b4 = New-Btn "Stop" 260 60 ([System.Drawing.Color]::FromArgb(120, 80, 30))
$br = New-Btn "Refresh" 325 30 ([System.Drawing.Color]::FromArgb(80, 80, 80))
$form.Controls.AddRange(@($b1, $b2, $b3, $b4, $br))

$lbl2 = New-Object System.Windows.Forms.Label
$lbl2.Text = "Host: $env:COMPUTERNAME"
$lbl2.Font = New-Object System.Drawing.Font("Segoe UI", 8)
$lbl2.ForeColor = [System.Drawing.Color]::FromArgb(80, 80, 80)
$lbl2.AutoSize = $true
$lbl2.Location = New-Object System.Drawing.Point(20, 160)
$form.Controls.Add($lbl2)

function Update-Status {
    $task = Get-ScheduledTask -TaskName $script:TaskName -ErrorAction SilentlyContinue
    if ($task) {
        $s = $task.State.ToString()
        $lbl.Text = "Status: $s"
        $b1.Enabled = $false; $b2.Enabled = $true
        $b3.Enabled = ($s -ne "Running"); $b4.Enabled = ($s -eq "Running")
    } else {
        $lbl.Text = "Not Installed"
        $b1.Enabled = $true; $b2.Enabled = $false; $b3.Enabled = $false; $b4.Enabled = $false
    }
}

$b1.Add_Click({
    $action = New-ScheduledTaskAction -Execute $script:ExePath
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
    Register-ScheduledTask -TaskName $script:TaskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
    Update-Status
})

$b2.Add_Click({
    $r = [System.Windows.Forms.MessageBox]::Show("Remove Monitor Agent?", "Confirm", "YesNo")
    if ($r -eq "Yes") {
        Stop-ScheduledTask -TaskName $script:TaskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $script:TaskName -Confirm:$false
        Update-Status
    }
})

$b3.Add_Click({ Start-ScheduledTask -TaskName $script:TaskName; Update-Status })
$b4.Add_Click({ Stop-ScheduledTask -TaskName $script:TaskName; Update-Status })
$br.Add_Click({ Update-Status })

Update-Status
[void]$form.ShowDialog()
