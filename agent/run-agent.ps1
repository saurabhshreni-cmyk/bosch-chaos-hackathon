[CmdletBinding()]
param(
    [string]$Model = 'qwen2.5:1.5b',
    [ValidateRange(1, 4)][int]$MaxExperiments = 3,
    [ValidateRange(3, 600)][int]$BaselineSeconds = 180,
    [switch]$Execute,
    [switch]$RuleBased,
    [switch]$AutoDiscover,
    [switch]$DetectOnly,
    [ValidatePattern('^\d{8}T\d{9}Z$')][string]$SessionId,
    [ValidateSet('workshop-crash', 'database-crash', 'rabbitmq-crash', 'workshop-delay', 'workshop-delay-high', 'workshop-crash-with-load')]
    [string[]]$ExperimentIds = @('workshop-crash', 'database-crash', 'workshop-delay', 'rabbitmq-crash')
)

$ErrorActionPreference = 'Stop'
if ($DetectOnly -and $Execute) { throw 'DetectOnly is read-only and cannot be combined with Execute.' }
if ($DetectOnly) { $AutoDiscover = $true }
Import-Module (Join-Path $PSScriptRoot 'AgentTools.psm1') -Force
Import-Module (Join-Path $PSScriptRoot 'Evidence.psm1') -Force
Import-Module (Join-Path $PSScriptRoot 'Telemetry.psm1') -Force
$repo = Split-Path $PSScriptRoot -Parent
$scripts = Join-Path $repo 'chaos-scripts'
$stopPath = Join-Path $scripts 'STOP'
$runId = $(if ($SessionId) { $SessionId } else { [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ') })
$output = Join-Path $PSScriptRoot "runs/$runId"
if ($SessionId -and (Test-Path $output)) { throw 'Session already exists; refusing to overwrite it.' }
$startedUtc = [DateTime]::UtcNow.ToString('o')
$events = [System.Collections.Generic.List[object]]::new()
$completed = [System.Collections.Generic.List[object]]::new()
$plans = [System.Collections.Generic.List[object]]::new()
$rankings = @()
$workers = [ordered]@{}
foreach ($role in @('Discovery', 'Planner', 'Injection', 'Detection', 'Recommendation')) {
    $workers[$role] = [pscustomobject]@{ Role = $role; Status = 'Idle'; ProcessId = $null; UpdatedUtc = $null; Error = $null }
}
$workerSequence = 0
$discovery = $null
$errorText = $null
$lock = $null
$mode = $(if ($RuleBased) { 'Rule-based; no AI used' } else { "AI: $Model" })
if ($DetectOnly) { $mode = 'Detection only; no catalog, planning or injection' }
$catalog = @()
if (-not $DetectOnly) { $catalog = Get-Content (Join-Path $PSScriptRoot 'experiments.json') -Raw | ConvertFrom-Json }
$dependencies = Get-Content (Join-Path $PSScriptRoot 'dependencies.json') -Raw | ConvertFrom-Json
$available = @($ExperimentIds | Select-Object -Unique)
New-Item -ItemType Directory -Path $output -Force | Out-Null

function Save-Progress {
    param([string]$Stage)
    $updatedUtc = [DateTime]::UtcNow.ToString('o')
    $events.Add([pscustomobject]@{ TimestampUtc = $updatedUtc; Stage = $Stage })
    $snapshot = [ordered]@{ RunId = $runId; StartedUtc = $startedUtc; UpdatedUtc = $updatedUtc; MaxExperiments = $MaxExperiments; BaselineSeconds = $BaselineSeconds; Events = @($events.ToArray()); Stage = $Stage; Mode = $mode; Execute = [bool]$Execute; Model = $(if (-not $RuleBased) { $Model } else { $null }); Rankings = @($rankings); Plans = @($plans.ToArray()); Experiments = @($completed.ToArray()); Error = $errorText }
    $snapshot.Workers = @($workers.Values)
    $snapshot.AutoDiscover = [bool]$AutoDiscover
    $snapshot.DetectOnly = [bool]$DetectOnly
    if ($DetectOnly) { $snapshot.Model = $null }
    $snapshot.Discovery = $discovery
    $snapshot.Architecture = 'Coordinator with isolated role workers; one fault at a time; continuous read-only dashboard detector runs independently.'
    Write-AgentSnapshot -Path (Join-Path $output 'session.json') -Value $snapshot -Required
    Write-Host "Agent: $Stage"
}

function Invoke-RoleWorker {
    param([string]$Role, $Request)
    if (Test-Path $stopPath) {
        if ($Role -in @('Discovery','Planner','Injection')) { throw 'Manual kill switch: no new worker started.' }
        if ($Role -eq 'Recommendation') { $Request.Remove('Model') }
    }
    $script:workerSequence++
    $directory = Join-Path $output "workers/$($script:workerSequence)-$Role"
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    $requestPath = Join-Path $directory 'request.json'
    $responsePath = Join-Path $directory 'response.json'
    Write-AgentSnapshot -Path $requestPath -Value $Request -Required
    $state = $workers[$Role]
    $state.Status = 'Running'; $state.Error = $null; $state.UpdatedUtc = [DateTime]::UtcNow.ToString('o')
    $process = $null
    try {
        $arguments = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"{0}"' -f (Join-Path $PSScriptRoot 'worker.ps1')), '-Role', $Role, '-RequestPath', ('"{0}"' -f $requestPath), '-ResponsePath', ('"{0}"' -f $responsePath))
        $process = Start-Process -FilePath (Join-Path $PSHOME 'powershell.exe') -ArgumentList $arguments -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $directory 'stdout.log') -RedirectStandardError (Join-Path $directory 'stderr.log')
        # Retain the Windows process handle before exit so ExitCode remains available.
        $null = $process.Handle
        $state.ProcessId = $process.Id
        Save-Progress "$Role worker running"
        while (-not $process.WaitForExit(100)) {
            if ((Test-Path $stopPath) -and $Role -in @('Planner','Recommendation')) {
                # These workers cannot own a fault; the injection worker must finish cleanup.
                $process.Kill()
                $process.WaitForExit()
                $state.Status = 'Cancelled'
                if ($Role -eq 'Recommendation') {
                    return @{ Result = @{ AnalysisPath = $Request.DetectionPath }; Error = $null }
                }
                throw 'Manual kill switch: AI planning cancelled.'
            }
        }
        if (-not (Test-Path -LiteralPath $responsePath)) { throw "$Role worker exited without a response; inspect $directory." }
        $response = Get-Content -LiteralPath $responsePath -Raw | ConvertFrom-Json
        if ($response.Role -ne $Role -or $response.ProcessId -ne $process.Id) { throw 'Worker response identity mismatch.' }
        if ($null -ne $process.ExitCode -and $process.ExitCode -ne 0 -and -not $response.Error) { throw "$Role worker exited unsuccessfully." }
        $state.Status = $(if ($response.Error) { 'Failed' } else { 'Completed' }); $state.Error = $response.Error
        return $response
    } catch {
        $state.Status = 'Failed'; $state.Error = $_.Exception.Message
        throw
    } finally {
        # Never abandon an injection child while it owns restoration responsibility.
        if ($process) { $process.WaitForExit(); $process.Dispose() }
        $state.UpdatedUtc = [DateTime]::UtcNow.ToString('o')
        Save-Progress "$Role worker $($state.Status.ToLower())"
    }
}

try {
    $lock = [IO.File]::Open((Join-Path $PSScriptRoot 'agent.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
    if (Test-Path $stopPath) { throw 'STOP file exists; remove it before running.' }
    if (-not $RuleBased -and -not $DetectOnly) {
        $models = Invoke-RestMethod 'http://localhost:11434/api/tags' -TimeoutSec 5
        if ($Model -notin @($models.models.name)) { throw "Model $Model is not installed. Run agent/setup-ai.ps1 or use -RuleBased explicitly." }
    }
    Save-Progress 'Collecting baseline'
    $baselinePath = & (Join-Path $PSScriptRoot 'baseline.ps1') -DurationSeconds $BaselineSeconds -OutputDirectory $output
    $baseline = Get-Content -LiteralPath $baselinePath -Raw | ConvertFrom-Json
    if ($AutoDiscover) {
        $incidents = @()
        $historyPath = Join-Path $PSScriptRoot 'monitor/incidents.json'
        if (Test-Path -LiteralPath $historyPath) {
            if ((Get-Item -LiteralPath $historyPath).Length -gt 4000000) { throw 'Monitor history exceeds discovery input limit.' }
            $incidents = @((Get-Content -LiteralPath $historyPath -Raw | ConvertFrom-Json).incidents)
        }
        $response = Invoke-RoleWorker -Role Discovery -Request @{ Baseline = $baseline; Dependencies = $dependencies; Catalog = @($catalog | Where-Object { $_.id -in $available }); Incidents = $incidents }
        if ($response.Error) { throw $response.Error }
        $discovery = $response.Result
        Write-AgentSnapshot -Path (Join-Path $output 'discovery.json') -Value $discovery -Required
        $available = @($discovery.Candidates.Id)
        Save-Progress 'Discovery recorded'
    }
    if ($DetectOnly) {
        Save-Progress 'Detection complete; no faults injected'
        return
    }
    if (-not $baseline.Healthy) { throw 'Unhealthy baseline: no faults will be injected.' }
    if (-not $RuleBased) {
        Save-Progress 'Ranking experiments'
        $response = Invoke-RoleWorker -Role Planner -Request @{ Model = $Model; Dependencies = $dependencies; Baseline = $baseline; Discovery = $discovery; Catalog = @($catalog | Where-Object { $_.id -in $available }) }
        if ($response.Error) { throw $response.Error }
        $rankings = @($response.Result)
        Save-Progress 'Ranked plan validated'
    }
    $experimentBudget = [math]::Min($MaxExperiments, $available.Count)
    for ($index = 0; $index -lt $experimentBudget; $index++) {
        if (Test-Path $stopPath) { throw 'Manual kill switch: agent stopped.' }
        Save-Progress 'Planning'
        $remaining = @($catalog | Where-Object { $_.id -in $available })
        if ($RuleBased) {
            $entry = @($remaining | Where-Object id -eq $available[0])[0]
            $plan = [pscustomobject]@{ id = $entry.id; durationSeconds = $entry.defaultDurationSeconds; reason = $entry.reason; expectedImpact = 'Measure page availability, latency, and verified recovery; this is a fixed catalog plan.' }
        }
        else { $plan = $rankings[$index] }
        Assert-ExperimentPlan -Plan $plan -AvailableIds $available
        $plans.Add($plan)
        $available = @($available | Where-Object { $_ -ne $plan.id })
        Write-Host "Selected $($plan.id): $($plan.reason)"
        Save-Progress 'Plan validated'
        if (-not $Execute) { continue }

        $savedReport = $null
        Save-Progress "Executing $($plan.id)"
        try {
            $response = Invoke-RoleWorker -Role Injection -Request @{ Plan = $plan; AvailableIds = @($ExperimentIds); ProgressPath = (Join-Path $output 'live-experiment.json') }
            $savedReport = $response.Result.ReportPath
            if ($response.Error) { throw $response.Error }
        }
        finally {
            if ($savedReport -and (Test-Path -LiteralPath $savedReport)) {
                Save-Progress "Analyzing $($plan.id)"
                $detected = Invoke-RoleWorker -Role Detection -Request @{ ReportPath = $savedReport }
                if ($detected.Error) { throw $detected.Error }
                $analysisParameters = @{ ReportPath = $savedReport; DetectionPath = $detected.Result.AnalysisPath }
                if (-not $RuleBased) { $analysisParameters.Model = $Model }
                $recommended = Invoke-RoleWorker -Role Recommendation -Request $analysisParameters
                $analysisPath = $recommended.Result.AnalysisPath
                if (-not $analysisPath) { throw "Recommendation worker failed: $($recommended.Error)" }
                $result = Get-Content -LiteralPath $savedReport -Raw | ConvertFrom-Json
                $analysis = Get-Content -LiteralPath $analysisPath -Raw | ConvertFrom-Json
                $completed.Add([pscustomobject]@{
                    ExperimentId = $plan.id; RunId = $result.RunId; Category = @($catalog | Where-Object id -eq $plan.id)[0].category
                    ReportPath = $savedReport; AnalysisPath = $analysisPath
                    Recovered = $result.Recovered; RecoverySeconds = $result.RecoverySeconds
                    RollbackReason = $result.RollbackReason; AnomalyCount = @($analysis.Anomalies).Count
                    AiStatus = $analysis.AiStatus
                    ProbeScore = Get-ProbeScore $result
                })
                Save-Progress 'Recovery and analysis recorded'
            }
        }
        if (-not $result.Recovered) { throw 'Recovery failed: aborting the remaining experiment budget.' }
        if (Test-Path $stopPath) { Save-Progress 'Stopped safely; fault restoration verified'; return }
        if (-not $RuleBased -and $analysis.AiStatus -notlike 'Completed*') { throw 'AI analysis failed; evidence saved, remaining experiments aborted.' }
    }
    Save-Progress $(if ($Execute) { 'Completed' } else { 'Plans only; no faults injected' })
}
catch {
    if ($_.Exception.Message -like 'Manual kill switch:*' -or $_.Exception.Message -eq 'Baseline cancelled by STOP file.') {
        Save-Progress 'Stopped safely; no new faults scheduled'
    } else { $errorText = $_.Exception.Message; Save-Progress 'Stopped with error' }
}
finally {
    $lines = [System.Collections.Generic.List[string]]::new()
    $lines.Add('# Chaos Agent Findings')
    $lines.Add('')
    $lines.Add("Run: $runId. Mode: $mode. Execute: $Execute.")
    $lines.Add('')
    $lines.Add(("Error: $errorText").TrimEnd())
    $lines.Add('')
    if ($discovery) {
        $lines.Add('## Observed Failures And Risks')
        foreach ($finding in @($discovery.Findings)) {
            $lines.Add("- [$($finding.Type)] $($finding.Subject): $($finding.Summary) Source: $($finding.Source).")
        }
        if ($DetectOnly) { $lines.Add('Read-only detection: no experiment catalog loaded, no AI planner called and no fault injected. Potential risks and historical incidents are not current failures. Continuous incident explanations and fixes are available in the dashboard Failure monitor.') }
        $lines.Add('')
    }
    $rankedFindings = [System.Collections.Generic.List[object]]::new()
    foreach ($entry in $completed) {
        $lines.Add("## $($entry.ExperimentId)")
        $lines.Add('')
        $lines.Add("Recovered: $($entry.Recovered). Recovery: $($entry.RecoverySeconds) s. Anomalies: $($entry.AnomalyCount). Rollback: $($entry.RollbackReason).")
        $lines.Add('')
        $lines.Add("Evidence run: $($entry.RunId). AI status: $($entry.AiStatus).")
        $lines.Add("Read-probe heuristic score: $($entry.ProbeScore.Value)/100. $($entry.ProbeScore.Method)")
        $lines.Add('')
        $analysis = Get-Content -LiteralPath $entry.AnalysisPath -Raw | ConvertFrom-Json
        $findings = @($analysis.AiFindings | Sort-Object @{ Expression = { switch ($_.severity) { high { 0 } medium { 1 } default { 2 } } } })
        foreach ($finding in $findings) {
            if ($finding) { $rankedFindings.Add([pscustomobject]@{ Experiment = $entry.ExperimentId; RunId = $entry.RunId; Finding = $finding }) }
        }
        if ($RuleBased) { $lines.Add('Measured anomalies only. No AI findings were generated.') }
        $lines.Add('')
    }
    if ($rankedFindings.Count -gt 0) {
        $lines.Add('## Ranked AI Findings')
        $lines.Add('')
        foreach ($item in @($rankedFindings | Sort-Object @{ Expression = { switch ($_.Finding.severity) { high { 0 } medium { 1 } default { 2 } } } })) {
            $finding = $item.Finding
            $lines.Add("- [$($finding.severity)] $($finding.title) ($($item.Experiment)): $($finding.explanation) Fix: $($finding.recommendedFix). Evidence: $($item.RunId)/$($finding.evidenceIds -join ', '). Confidence: $($finding.confidence).")
        }
        $lines.Add('')
    }
    $lines.Add('Read probes do not prove write correctness or message durability. ProbeScore is a transparent heuristic, not AI-generated or a calibrated SLA. Review AI interpretations against evidence.')
    $lines | Set-Content (Join-Path $output 'findings.md') -Encoding UTF8
    if ($lock) { $lock.Dispose() }
    Write-Host "Session and findings: $output"
}
if ($errorText) { throw $errorText }
