[CmdletBinding()]
param(
    [ValidateSet('workshopmanagementapi', 'sqlserver', 'rabbitmq')][string]$TargetService = 'workshopmanagementapi',
    [ValidateSet('Crash', 'NetworkDelay')][string]$FailureType = 'Crash',
    [ValidateRange(100, 1000)][int]$DelayMilliseconds = 500,
    [ValidateRange(1, 3)][int]$MaxImpactedModules = 2,
    [ValidateRange(1, 60)][int]$DurationSeconds = 30,
    [ValidateRange(1, 10)][int]$RequestTimeoutSeconds = 5,
    [ValidateRange(1, 10)][int]$BaselineRounds = 3,
    [ValidateRange(1, 30000)][int]$MaxUnaffectedLatencyMs = 3000,
    [ValidateRange(10, 180)][int]$RecoveryTimeoutSeconds = 90,
    [ref]$ResultReportPath
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$composeFile = Join-Path $repo 'src/docker-compose.yml'
$stopFile = Join-Path $PSScriptRoot 'STOP'
$runId = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
$outputDir = Join-Path $PSScriptRoot "results/$runId"
$samples = [System.Collections.Generic.List[object]]::new()
$modules = @('CustomerManagement', 'VehicleManagement', 'WorkshopManagement')
$impacted = [System.Collections.Generic.HashSet[string]]::new()
$reportPath = Join-Path $outputDir 'report.json'
$container = $null
$watchdog = $null
$injected = $false
$restored = $false
$recovered = $false
$reason = 'Not injected'
$failure = $null
$faultAt = $null
$restoreAt = $null
$recoveredAt = $null
$lock = $null
$netImage = 'nicolaka/netshoot:v0.13'
$brokerBefore = $null
$brokerAfter = $null

function Invoke-Docker {
    param([string[]]$DockerArgs)
    $result = & docker @DockerArgs 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Docker failed: $result" }
    return $result
}

function Measure-Module {
    param([string]$Module, [string]$Phase)
    $timer = [Diagnostics.Stopwatch]::StartNew()
    $status = $null
    $offline = $false
    $healthy = $false
    $errorText = $null
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:7005/$Module" -UseBasicParsing -TimeoutSec $RequestTimeoutSeconds
        $status = [int]$response.StatusCode
        $offline = $response.Content -match '(?i)module is offline|management\s*-\s*offline'
        $healthy = $status -eq 200 -and -not $offline -and $response.Content -match ($Module -replace 'Management', ' Management')
    }
    catch { $errorText = $_.Exception.Message }
    $timer.Stop()
    $sample = [pscustomobject]@{
        TimestampUtc = [DateTime]::UtcNow.ToString('o'); Phase = $Phase
        Module = $Module; StatusCode = $status; OfflinePage = $offline
        Healthy = $healthy; LatencyMs = [math]::Round($timer.Elapsed.TotalMilliseconds, 1)
        Error = $errorText
    }
    $samples.Add($sample)
    Write-Host "$Phase $Module healthy=$healthy status=$status latency=$($sample.LatencyMs)ms"
    return $sample
}

function Invoke-TrafficControl {
    param([string[]]$TcArgs)
    Invoke-Docker -DockerArgs (@('run', '--rm', '--pull=never', '--network', "container:$container", '--cap-add', 'NET_ADMIN', $netImage, 'tc') + $TcArgs)
}

function Restore-Target {
    if ($FailureType -eq 'Crash') {
        Invoke-Docker -DockerArgs @('start', $container) | Out-Null
    }
    else {
        $qdisc = Invoke-TrafficControl -TcArgs @('qdisc', 'show', 'dev', 'eth0') | Out-String
        if ($qdisc -match 'qdisc netem 28: root') {
            Invoke-TrafficControl -TcArgs @('qdisc', 'del', 'dev', 'eth0', 'root', 'handle', '28:') | Out-Null
        }
    }
}

try {
try {
    if (Test-Path $stopFile) { throw "Remove $stopFile before starting a new experiment." }
    if ($FailureType -eq 'NetworkDelay' -and $TargetService -ne 'workshopmanagementapi') { throw 'Network delay is allowed only on Workshop API.' }
    $context = (Invoke-Docker -DockerArgs @('context', 'show') | Out-String).Trim()
    $endpoint = (Invoke-Docker -DockerArgs @('context', 'inspect', $context, '--format', '{{.Endpoints.docker.Host}}') | Out-String).Trim()
    if ($env:DOCKER_HOST -or $endpoint -notmatch '^npipe://') { throw 'This experiment requires a local Windows Docker named-pipe context.' }
    $ids = @(Invoke-Docker -DockerArgs @('compose', '-f', $composeFile, 'ps', '-q', $TargetService))
    if ($ids.Count -ne 1 -or -not $ids[0]) { throw "Expected exactly one running $TargetService container." }
    $container = "$($ids[0])".Trim()
    $details = (Invoke-Docker -DockerArgs @('inspect', $container) | Out-String) | ConvertFrom-Json
    $labels = $details[0].Config.Labels
    $project = $labels.'com.docker.compose.project'
    $configFiles = @(([string]$labels.'com.docker.compose.project.config_files') -split ',' | Where-Object { $_ } | ForEach-Object { [IO.Path]::GetFullPath($_) })
    if ($labels.'com.docker.compose.service' -ne $TargetService -or [IO.Path]::GetFullPath($composeFile) -notin $configFiles) {
        throw 'Refusing a container that is not owned by this checkout Compose configuration.'
    }
    $lockPath = Join-Path $PSScriptRoot 'experiment.lock'
    $lock = [System.IO.File]::Open($lockPath, 'OpenOrCreate', 'ReadWrite', 'None')
    Write-Host "Target: $TargetService (Compose project: $project)"
    if ($FailureType -eq 'NetworkDelay') {
        Invoke-Docker -DockerArgs @('image', 'inspect', '--format', '{{.Id}}', $netImage) | Out-Null
        $qdisc = Invoke-TrafficControl -TcArgs @('qdisc', 'show', 'dev', 'eth0') | Out-String
        if ($qdisc -notmatch 'qdisc noqueue 0: root' -or $qdisc -match 'netem') {
            throw 'Refusing to replace an existing non-default traffic-control configuration.'
        }
    }

    New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
    if ($ResultReportPath) { $ResultReportPath.Value = $reportPath }
    if ($TargetService -eq 'rabbitmq') {
        $brokerBefore = (Invoke-Docker -DockerArgs @('exec', $container, 'rabbitmqctl', 'list_queues', 'name', 'messages_ready', 'messages_unacknowledged', 'durable', '--formatter', 'json') | Out-String) | ConvertFrom-Json
    }
    for ($round = 0; $round -lt $BaselineRounds; $round++) {
        foreach ($module in $modules) {
            $sample = Measure-Module $module 'baseline'
            if (-not $sample.Healthy) {
                throw "Baseline failed for $module. No fault was injected."
            }
        }
        Start-Sleep -Seconds 1
    }

    if (Test-Path $stopFile) { throw 'Manual kill switch activated during baseline. No fault was injected.' }

    # The independent watchdog restores the service even if a request stalls.
    $watchdog = Start-Job -ArgumentList $container, $DurationSeconds, $FailureType, $netImage -ScriptBlock {
        param($target, $duration, $type, $image)
        Start-Sleep -Seconds $duration
        if ($type -eq 'Crash') { & docker start $target }
        else {
            $qdisc = & docker run --rm --pull=never --network "container:$target" --cap-add NET_ADMIN $image tc qdisc show dev eth0
            if ($LASTEXITCODE -ne 0) { throw 'Watchdog traffic-control check failed.' }
            if ($qdisc -match 'qdisc netem 28: root') {
                & docker run --rm --pull=never --network "container:$target" --cap-add NET_ADMIN $image tc qdisc del dev eth0 root handle 28:
            }
        }
        if ($LASTEXITCODE -ne 0) { throw 'Watchdog could not restore the container.' }
    }
    $injected = $true
    $faultAt = [DateTime]::UtcNow
    if ($FailureType -eq 'Crash') { Invoke-Docker -DockerArgs @('kill', $container) | Out-Null }
    else { Invoke-TrafficControl -TcArgs @('qdisc', 'add', 'dev', 'eth0', 'root', 'handle', '28:', 'netem', 'delay', "${DelayMilliseconds}ms") | Out-Null }
    $reason = 'Maximum fault duration reached'
    $faultTimer = [Diagnostics.Stopwatch]::StartNew()
    :FaultLoop while ($faultTimer.Elapsed.TotalSeconds -lt $DurationSeconds) {
        foreach ($module in $modules) {
            if (Test-Path $stopFile) { $reason = 'Manual kill switch'; break FaultLoop }
            if ($faultTimer.Elapsed.TotalSeconds -ge $DurationSeconds) { break FaultLoop }
            $sample = Measure-Module $module 'fault'
            if (-not $sample.Healthy) { [void]$impacted.Add($module) }
            if ($TargetService -in @('sqlserver', 'rabbitmq') -and $impacted.Count -ge $MaxImpactedModules) {
                $reason = "Safety threshold breached: $($impacted.Count) modules impacted"
                break FaultLoop
            }
            if ($TargetService -eq 'workshopmanagementapi' -and $module -ne 'WorkshopManagement' -and (-not $sample.Healthy -or $sample.LatencyMs -gt $MaxUnaffectedLatencyMs)) {
                $reason = "Safety threshold breached: $module"
                break FaultLoop
            }
        }
        Start-Sleep -Seconds 1
    }
}
catch { $failure = $_.Exception.Message; $reason = "Experiment error: $failure" }
finally {
    if ($injected) {
        try {
            Restore-Target
            $restored = $true
            $restoreAt = [DateTime]::UtcNow
        }
        catch { $failure = "Restore failed: $($_.Exception.Message)" }
    }
    if ($watchdog -and $restored) {
        Stop-Job $watchdog
        Remove-Job $watchdog -Force
    }
    elseif ($watchdog) {
        Wait-Job $watchdog -Timeout ($DurationSeconds + 10) | Out-Null
        Receive-Job $watchdog -ErrorAction Continue | Out-Host
    }
}

if ($restored) {
    $recoveryTimer = [Diagnostics.Stopwatch]::StartNew()
    while ($recoveryTimer.Elapsed.TotalSeconds -lt $RecoveryTimeoutSeconds) {
        $roundHealthy = $true
        foreach ($module in $modules) {
            if (-not (Measure-Module $module 'recovery').Healthy) { $roundHealthy = $false }
        }
        if ($TargetService -eq 'rabbitmq') {
            try { Invoke-Docker -DockerArgs @('exec', $container, 'rabbitmq-diagnostics', '-q', 'check_running') | Out-Null }
            catch { $roundHealthy = $false }
        }
        if ($roundHealthy) { $recovered = $true; $recoveredAt = [DateTime]::UtcNow; break }
        Start-Sleep -Seconds 2
    }
}

if ($TargetService -eq 'rabbitmq' -and $recovered) {
    try { $brokerAfter = (Invoke-Docker -DockerArgs @('exec', $container, 'rabbitmqctl', 'list_queues', 'name', 'messages_ready', 'messages_unacknowledged', 'durable', '--formatter', 'json') | Out-String) | ConvertFrom-Json }
    catch { $failure = "Broker snapshot failed: $($_.Exception.Message)" }
}

if (Test-Path $outputDir) {
    $samples | Export-Csv -Path (Join-Path $outputDir 'samples.csv') -NoTypeInformation
    $summary = [ordered]@{
        RunId = $runId; TargetService = $TargetService; ContainerId = $container
        FailureType = $FailureType; DelayMilliseconds = $(if ($FailureType -eq 'NetworkDelay') { $DelayMilliseconds } else { $null })
        MaxImpactedModules = $MaxImpactedModules
        BrokerQueuesBefore = @($brokerBefore); BrokerQueuesAfter = @($brokerAfter)
        RequestedDurationSeconds = $DurationSeconds; RollbackReason = $reason
        FaultStartedUtc = $faultAt; RestoreCommandCompletedUtc = $restoreAt; RecoveredUtc = $recoveredAt
        Restored = $restored; Recovered = $recovered; Error = $failure
        RecoverySeconds = $(if ($recovered) { [math]::Round(($recoveredAt - $restoreAt).TotalSeconds, 2) } else { $null })
        Samples = @($samples.ToArray())
    }
    $summary | ConvertTo-Json -Depth 6 | Set-Content -Path $reportPath -Encoding UTF8
    Write-Host "Results: $outputDir"
}
if ($failure -or -not $recovered) { throw "Experiment did not complete successfully. $failure Rollback: $reason" }
Write-Host "Service recovered. Rollback: $reason"
Write-Output $reportPath
}
finally { if ($lock) { $lock.Dispose() } }
