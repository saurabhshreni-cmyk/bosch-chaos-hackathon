<# Internal runner for the two fixed-target pause experiments.
Reuses main's ChaosSafety ownership, STOP and experiment.lock guards.
The detached PowerShell watchdog owns the shared lock from readiness through
verified recovery. It retries rollback if Docker is temporarily unavailable.
No daemon socket mount, privileged image, application writes, or LLM is needed.
#>
[CmdletBinding()]
param(
    [ValidateSet('customermanagementapi','vehiclemanagementapi')][string]$Service,
    [ValidateRange(5,60)][int]$DurationSeconds = 15,
    [ValidateRange(1,10)][int]$RequestTimeoutSeconds = 3,
    [ValidateRange(1,10)][int]$BaselineRounds = 3,
    [ValidateRange(1,30000)][int]$MaxUnaffectedLatencyMs = 3000,
    [ValidateRange(10,180)][int]$RecoveryTimeoutSeconds = 90,
    [switch]$Execute,
    [switch]$Watchdog,
    [string]$LeasePath
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'ChaosSafety.psm1') -Force
$compose = [IO.Path]::GetFullPath((Join-Path (Split-Path $PSScriptRoot -Parent) 'src/docker-compose.yml'))
$stopFile = Join-Path $PSScriptRoot 'STOP'
$lockPath = Join-Path $PSScriptRoot 'experiment.lock'
$modules = @('CustomerManagement','VehicleManagement','WorkshopManagement')
$dockerPath = (Get-Command docker -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source

function Invoke-PinnedDocker {
    param([string[]]$Arguments)
    $output = & $dockerPath --host $script:endpoint @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Docker operation failed: $output" }
    return $output
}
function Assert-PauseTarget {
    param([string]$Id, [string]$Name, [switch]$RequireUnpaused)
    $item = @((Invoke-PinnedDocker @('inspect',$Id) | Out-String | ConvertFrom-Json))[0]
    $labels = $item.Config.Labels
    $configs = @(([string]$labels.'com.docker.compose.project.config_files') -split ',' |
        Where-Object { $_ } | ForEach-Object { [IO.Path]::GetFullPath($_.Trim()) })
    if (-not $labels.'com.docker.compose.project' -or $labels.'com.docker.compose.service' -ne $Name -or $compose -notin $configs) {
        throw 'Container ownership does not match this checkout.'
    }
    if (-not $item.State.Running) { throw 'The target is not running.' }
    if ($RequireUnpaused -and $item.State.Paused) { throw 'Refusing a target that is already paused.' }
    return $item
}
function Restore-Pause {
    param([string]$Id, [string]$Name)
    $item = Assert-PauseTarget $Id $Name
    if ($item.State.Paused) { Invoke-PinnedDocker @('unpause',$Id) | Out-Null }
    return (-not (Assert-PauseTarget $Id $Name).State.Paused)
}
function Measure-Page {
    param([string]$Module, [string]$Phase)
    $timer = [Diagnostics.Stopwatch]::StartNew()
    $status = $null; $healthy = $false; $offline = $false; $message = $null
    try {
        $response = Invoke-WebRequest "http://127.0.0.1:7005/$Module" -TimeoutSec $RequestTimeoutSeconds -UseBasicParsing
        $status = [int]$response.StatusCode
        $offline = $response.Content -match '(?i)module is offline|management\s*-\s*offline'
        $healthy = $status -eq 200 -and $response.Content -notmatch '(?i)module is offline|management\s*-\s*offline' -and
            $response.Content -match ($Module -replace 'Management',' Management')
    } catch { $message = $_.Exception.Message }
    $timer.Stop()
    return [pscustomobject]@{ TimestampUtc=[DateTime]::UtcNow.ToString('o'); Phase=$Phase; Module=$Module
        StatusCode=$status; OfflinePage=$offline; Healthy=$healthy; LatencyMs=[math]::Round($timer.Elapsed.TotalMilliseconds,1); Error=$message }
}
function Test-AllPages {
    foreach ($module in $modules) { if (-not (Measure-Page $module 'watchdog-recovery').Healthy) { return $false } }
    return $true
}

if ($Watchdog) {
    $resultRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'results')) + [IO.Path]::DirectorySeparatorChar
    if (-not [IO.Path]::GetFullPath($LeasePath).StartsWith($resultRoot,[StringComparison]::OrdinalIgnoreCase)) {
        throw 'Watchdog lease must be inside chaos-scripts/results.'
    }
    $lease = Get-Content -LiteralPath $LeasePath -Raw | ConvertFrom-Json
    if ($lease.Service -notin @('customermanagementapi','vehiclemanagementapi') -or
        $lease.Endpoint -notmatch '^npipe://' -or $lease.DurationSeconds -lt 5 -or $lease.DurationSeconds -gt 60) {
        throw 'Invalid watchdog lease.'
    }
    $script:endpoint = $lease.Endpoint
    $directory = Split-Path $LeasePath -Parent
    $lock = Enter-ExperimentLock -Path $lockPath
    try {
        Assert-PauseTarget $lease.ContainerId $lease.Service -RequireUnpaused | Out-Null
        Set-Content (Join-Path $directory 'watchdog-ready') 'ready'
        $deadline = [DateTime]::UtcNow.AddSeconds([int]$lease.DurationSeconds)
        $rollingBack = $false
        while ($true) {
            $parent = Get-Process -Id $lease.ParentId -ErrorAction SilentlyContinue
            $parentAlive = $parent -and $parent.StartTime.ToUniversalTime().Ticks -eq ([DateTime]$lease.ParentStartedUtc).ToUniversalTime().Ticks
            $armed = Test-Path (Join-Path $directory 'armed')
            $done = Test-Path (Join-Path $directory 'completed')
            if ($done -or -not $parentAlive -or (Test-Path $stopFile) -or [DateTime]::UtcNow -ge $deadline) { $rollingBack = $true }
            if ($rollingBack) {
                try {
                    $restored = -not $armed -or (Restore-Pause $lease.ContainerId $lease.Service)
                    if ($restored -and ($done -or -not $parentAlive)) {
                        # A dead runner cannot verify recovery. Do so before releasing the shared lock.
                        if (-not $armed -or (Test-AllPages)) {
                            @{Restored=$true; Recovered=$true; TimestampUtc=[DateTime]::UtcNow.ToString('o')} |
                                ConvertTo-Json | Set-Content (Join-Path $directory 'watchdog-report.json') -Encoding utf8
                            break
                        }
                    }
                } catch {
                    $_.Exception.Message | Add-Content (Join-Path $directory 'watchdog-errors.log')
                }
            }
            Start-Sleep -Milliseconds 500
        }
    } finally { $lock.Dispose() }
    return
}

if (-not $Service) { throw 'Use pause-customer-api.ps1 or pause-vehicle-api.ps1.' }
$targetModule = if ($Service -eq 'customermanagementapi') { 'CustomerManagement' } else { 'VehicleManagement' }
$experiment = if ($Service -eq 'customermanagementapi') { 'pause-customer-api' } else { 'pause-vehicle-api' }
# Check the local endpoint before even resolving a Compose target. Pin all later calls to it.
if ($env:DOCKER_HOST -or $env:DOCKER_TLS_VERIFY) { throw 'Docker endpoint overrides are not allowed.' }
$context = (& $dockerPath context show | Out-String).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve Docker context.' }
$script:endpoint = (& $dockerPath context inspect $context --format '{{.Endpoints.docker.Host}}' | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $endpoint -notmatch '^npipe://') { throw 'Requires a local Windows Docker named-pipe endpoint.' }
$ids = @(Invoke-PinnedDocker @('compose','-f',$compose,'ps','-q',$Service))
if ($ids.Count -ne 1 -or -not $ids[0]) { throw "Expected one running $Service container." }
$container = ([string]$ids[0]).Trim()
Assert-PauseTarget $container $Service -RequireUnpaused | Out-Null
if (-not $Execute) {
    Write-Host "DRY RUN: would pause $Service for at most $DurationSeconds seconds, then unpause and verify all three pages."
    Write-Host "STOP engaged: $(Test-Path $stopFile). No changes made. Explicit -Execute is required."
    return
}
Assert-KillSwitchClear -StopFile $stopFile
$lock = $null; $guardian = $null; $armed = $false; $restored = $false; $recovered = $false
$faultAt = $null; $restoreAt = $null; $recoveredAt = $null; $failure = $null; $reason = 'Not injected'
$runId = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ') + '-' + [Guid]::NewGuid().ToString('N').Substring(0,6)
$outputDir = Join-Path $PSScriptRoot "results/$runId"
$samples = [Collections.Generic.List[object]]::new()
New-Item -ItemType Directory $outputDir -Force | Out-Null
try {
    $lock = Enter-ExperimentLock -Path $lockPath
    for ($round=0; $round -lt $BaselineRounds; $round++) {
        foreach ($module in $modules) {
            $sample = Measure-Page $module 'baseline'; $samples.Add($sample)
            if (-not $sample.Healthy -or $sample.LatencyMs -gt $MaxUnaffectedLatencyMs) { throw "Baseline failed for $module." }
        }
    }
    Assert-KillSwitchClear -StopFile $stopFile -Context 'after baseline'
    Assert-PauseTarget $container $Service -RequireUnpaused | Out-Null
    $leaseFile = Join-Path $outputDir 'lease.json'
    @{ Service=$Service; ContainerId=$container; Endpoint=$endpoint; DurationSeconds=$DurationSeconds
        ParentId=$PID; ParentStartedUtc=(Get-Process -Id $PID).StartTime.ToUniversalTime().ToString('o') } |
        ConvertTo-Json | Set-Content $leaseFile -Encoding utf8
    # Transfer the shared lock to the detached guardian. If another run takes it
    # during handoff, the guardian fails readiness and this run never injects.
    $lock.Dispose(); $lock=$null
    $runner = $PSCommandPath.Replace("'","''"); $leaseArg = $leaseFile.Replace("'","''")
    $command = "& '$runner' -Watchdog -LeasePath '$leaseArg'"
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
    $guardian = Start-Process -FilePath (Get-Process -Id $PID).Path -ArgumentList @('-NoProfile','-NonInteractive','-EncodedCommand',$encoded) -WindowStyle Hidden -PassThru
    $readyTimer = [Diagnostics.Stopwatch]::StartNew()
    while (-not (Test-Path (Join-Path $outputDir 'watchdog-ready'))) {
        if ($guardian.HasExited -or $readyTimer.Elapsed.TotalSeconds -gt 15) { throw 'Detached watchdog did not become ready. No fault injected.' }
        Start-Sleep -Milliseconds 100
    }
    Assert-KillSwitchClear -StopFile $stopFile -Context 'immediately before injection'
    if ($guardian.HasExited) { throw 'Watchdog exited before injection.' }
    # Arm BEFORE pause so even a failed or interrupted Docker call has rollback.
    Set-Content (Join-Path $outputDir 'armed') 'armed'; $armed=$true
    $faultAt=[DateTime]::UtcNow
    Invoke-PinnedDocker @('pause',$container) | Out-Null
    if (-not (Assert-PauseTarget $container $Service).State.Paused) { throw 'Pause was not applied.' }
    $reason='Maximum fault duration reached'
    $deadline=$faultAt.AddSeconds($DurationSeconds)
    :Fault while ([DateTime]::UtcNow -lt $deadline) {
        foreach ($module in $modules) {
            if (Test-Path $stopFile) { $reason='Manual kill switch'; break Fault }
            if ([DateTime]::UtcNow -ge $deadline) { break Fault }
            $sample=Measure-Page $module 'fault'; $samples.Add($sample)
            if ($module -ne $targetModule -and (-not $sample.Healthy -or $sample.LatencyMs -gt $MaxUnaffectedLatencyMs)) {
                $reason="Safety threshold breached: $module"; break Fault
            }
        }
        Start-Sleep -Milliseconds 200
    }
} catch { $failure=$_.Exception.Message; $reason="Experiment error: $failure" }
finally {
    if ($armed) {
        try { $restored=Restore-Pause $container $Service; $restoreAt=[DateTime]::UtcNow }
        catch { $failure="Rollback failed: $($_.Exception.Message). Detached watchdog remains responsible." }
    }
    if ($lock) { $lock.Dispose() }
}
if ($restored) {
    $timer=[Diagnostics.Stopwatch]::StartNew()
    while ($timer.Elapsed.TotalSeconds -lt $RecoveryTimeoutSeconds) {
        $roundHealthy=$true
        foreach ($module in $modules) {
            $sample=Measure-Page $module 'recovery'; $samples.Add($sample)
            if (-not $sample.Healthy -or $sample.LatencyMs -gt $MaxUnaffectedLatencyMs) { $roundHealthy=$false }
        }
        if ($roundHealthy) { $recovered=$true; $recoveredAt=[DateTime]::UtcNow; break }
        Start-Sleep -Seconds 1
    }
}
if ($samples.Count) { $samples.ToArray() | Export-Csv (Join-Path $outputDir 'samples.csv') -NoTypeInformation }
else { 'TimestampUtc,Phase,Module,StatusCode,Healthy,LatencyMs,Error' | Set-Content (Join-Path $outputDir 'samples.csv') }
@{RunId=$runId; Experiment=$experiment; TargetService=$Service; ContainerId=$container; RequestedDurationSeconds=$DurationSeconds
    FaultStartedUtc=$faultAt; RestoreCommandCompletedUtc=$restoreAt; RecoveredUtc=$recoveredAt
    Restored=$restored; Recovered=$recovered; Error=$failure; RollbackReason=$reason
    RecoverySeconds=$(if($recovered){[math]::Round(($recoveredAt-$restoreAt).TotalSeconds,2)}else{$null})
    WatchdogProcessId=$(if($guardian){$guardian.Id}else{$null}); Samples=@($samples.ToArray())
    RecoveryBasis='Container unpaused and all three module pages healthy within the latency threshold. No write-path recovery claim.'} |
    ConvertTo-Json -Depth 6 | Set-Content (Join-Path $outputDir 'report.json') -Encoding utf8
# Never stop a guardian when restoration or measured recovery is uncertain.
if (-not $armed -or ($restored -and $recovered)) {
    Set-Content (Join-Path $outputDir 'completed') 'completed'
    if ($guardian) { $guardian.WaitForExit(10000) | Out-Null }
}
Write-Host "Results: $outputDir"
if ($failure -or -not $recovered) { throw "Experiment incomplete: $failure. $reason. Keep STOP engaged and inspect watchdog-report.json." }
Write-Host 'Pause removed and page recovery verified.'
