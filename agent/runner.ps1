param(
    [string]$InstallDir = (Join-Path $env:ProgramData "GameFrameRateViewer")
)

$ErrorActionPreference = "Stop"

$ConfigPath = Join-Path $InstallDir "updater\updater-config.json"
$FallbackConfigPath = Join-Path $InstallDir "config.json"
$UpdaterPath = Join-Path $InstallDir "updater\updater.ps1"
$DownloadDir = Join-Path $InstallDir "downloads"
$LogDir = Join-Path $InstallDir "logs"
$LogPath = Join-Path $LogDir "runner.log"

function Write-RunnerLog {
    param([string]$Message)
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
    Add-Content -Path $LogPath -Value ("[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message) -Encoding UTF8
}

function Read-JsonFile {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return @{} }
    try {
        return Get-Content -Path $Path -Encoding UTF8 -Raw | ConvertFrom-Json
    } catch {
        Write-RunnerLog "Read config failed ${Path}: $($_.Exception.Message)"
        return @{}
    }
}

function Get-ConfigValue {
    param($Primary, $Fallback, [string]$Name, $Default = "")
    if ($Primary -and $Primary.PSObject.Properties.Name -contains $Name -and -not [string]::IsNullOrWhiteSpace([string]$Primary.$Name)) {
        return [string]$Primary.$Name
    }
    if ($Fallback -and $Fallback.PSObject.Properties.Name -contains $Name -and -not [string]::IsNullOrWhiteSpace([string]$Fallback.$Name)) {
        return [string]$Fallback.$Name
    }
    return $Default
}

function Invoke-JsonApi {
    param(
        [string]$Method,
        [string]$Url,
        $Body = $null
    )
    $args = @{
        Method = $Method
        Uri = $Url
        TimeoutSec = 30
        UseBasicParsing = $true
    }
    if ($Body -ne $null) {
        $args.ContentType = "application/json; charset=utf-8"
        $args.Body = ($Body | ConvertTo-Json -Depth 8)
    }
    return Invoke-RestMethod @args
}

function Report-Job {
    param(
        [string]$ServerUrl,
        [string]$JobId,
        [string]$Status,
        [string]$Message = "",
        [string]$ErrorMessage = "",
        [int64]$ProgressBytes = -1,
        [int64]$TotalBytes = -1
    )
    if ([string]::IsNullOrWhiteSpace($JobId)) { return }
    $body = @{
        status = $Status
        message = $Message
        error = $ErrorMessage
    }
    if ($ProgressBytes -ge 0) { $body.progress_bytes = $ProgressBytes }
    if ($TotalBytes -ge 0) { $body.total_bytes = $TotalBytes }
    try {
        Invoke-JsonApi -Method "POST" -Url "$ServerUrl/api/updater/jobs/$JobId/heartbeat" -Body $body | Out-Null
    } catch {
        Write-RunnerLog "Report job failed ${Status}: $($_.Exception.Message)"
    }
}

function Get-FileSha256 {
    param([string]$Path)
    return (Get-FileHash -Path $Path -Algorithm SHA256).Hash.ToUpperInvariant()
}

$primary = Read-JsonFile $ConfigPath
$fallback = Read-JsonFile $FallbackConfigPath
$serverHost = Get-ConfigValue $primary $fallback "server_host" "108.187.15.71"
$serverPort = Get-ConfigValue $primary $fallback "server_port" "8899"
$serverUrl = Get-ConfigValue $primary $fallback "server_url" "http://${serverHost}:${serverPort}"
$installId = Get-ConfigValue $primary $fallback "install_id" ""
$machineId = Get-ConfigValue $primary $fallback "machine_id" ""
$updaterVersion = Get-ConfigValue $primary $fallback "updater_version" "0.58.5"

try {
    if ([string]::IsNullOrWhiteSpace($installId) -or [string]::IsNullOrWhiteSpace($machineId)) {
        Write-RunnerLog "Skip: install_id or machine_id empty"
        exit 0
    }
    if (-not (Test-Path $UpdaterPath)) {
        throw "updater.ps1 not found: $UpdaterPath"
    }

    $nextUrl = '{0}/api/updater/jobs/next?install_id={1}&machine_id={2}&updater_version={3}' -f $serverUrl, [uri]::EscapeDataString($installId), [uri]::EscapeDataString($machineId), [uri]::EscapeDataString($updaterVersion)
    $next = Invoke-JsonApi -Method 'GET' -Url $nextUrl
    if (-not $next.job) {
        exit 0
    }

    $job = $next.job
    $version = $next.version
    $jobId = [string]$job.job_id
    $targetVersion = [string]$job.target_version
    $expectedSha = ([string]$version.sha256).ToUpperInvariant()
    $packageUrl = [string]$version.package_exe_url
    if (-not $packageUrl.StartsWith("http")) {
        $packageUrl = '{0}{1}' -f $serverUrl, $packageUrl
    }

    New-Item -ItemType Directory -Force -Path $DownloadDir | Out-Null
    $targetPath = Join-Path $DownloadDir ('GameFrameRateViewer-{0}.exe' -f $targetVersion)
    $tmpPath = '{0}.tmp' -f $targetPath
    $totalBytes = [int64]($version.size_bytes)

    if ((Test-Path $targetPath) -and (Get-FileSha256 $targetPath) -eq $expectedSha) {
        Report-Job -ServerUrl $serverUrl -JobId $jobId -Status 'downloaded' -Message '已复用本地缓存' -ProgressBytes $totalBytes -TotalBytes $totalBytes
    } else {
        Report-Job -ServerUrl $serverUrl -JobId $jobId -Status 'downloading' -Message '开始下载更新包' -ProgressBytes 0 -TotalBytes $totalBytes
        Remove-Item -LiteralPath $tmpPath -Force -ErrorAction SilentlyContinue
        Invoke-WebRequest -Uri $packageUrl -OutFile $tmpPath -UseBasicParsing
        $actualSha = Get-FileSha256 $tmpPath
        if ($expectedSha -and $actualSha -ne $expectedSha) {
            Remove-Item -LiteralPath $tmpPath -Force -ErrorAction SilentlyContinue
            throw ('sha256 mismatch {0} != {1}' -f $actualSha, $expectedSha)
        }
        Move-Item -LiteralPath $tmpPath -Destination $targetPath -Force
        $downloadedBytes = (Get-Item $targetPath).Length
        Report-Job -ServerUrl $serverUrl -JobId $jobId -Status 'downloaded' -Message '下载完成并校验通过' -ProgressBytes $downloadedBytes -TotalBytes $totalBytes
    }

    Report-Job -ServerUrl $serverUrl -JobId $jobId -Status 'installing' -Message '调用 updater 安装' -TotalBytes $totalBytes
    $args = @(
        '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
        '-File', $UpdaterPath,
        '-InstallDir', $InstallDir,
        '-NewExe', $targetPath,
        '-TargetVersion', $targetVersion,
        '-JobId', $jobId,
        '-InstallId', $installId,
        '-ServerUrl', $serverUrl
    )
    $proc = Start-Process -FilePath 'powershell.exe' -ArgumentList $args -WindowStyle Hidden -PassThru -Wait
    if ($proc.ExitCode -ne 0) {
        throw ('updater exited {0}' -f $proc.ExitCode)
    }
} catch {
    $message = $_.Exception.Message
    Write-RunnerLog ('Failed: {0}' -f $message)
    if ($jobId) {
        Report-Job -ServerUrl $serverUrl -JobId $jobId -Status 'failed' -ErrorMessage $message
    }
    exit 1
}
