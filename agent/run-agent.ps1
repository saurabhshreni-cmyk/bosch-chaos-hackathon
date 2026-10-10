[CmdletBinding()]
param(
    [string]$Model = 'qwen2.5:1.5b',
    [ValidateRange(1, 4)][int]$MaxExperiments = 3,
    [ValidateRange(3, 600)][int]$BaselineSeconds = 180,
    [switch]$Execute,
    [switch]$RuleBased,
    [ValidatePattern('^\d{8}T\d{9}Z$')][string]$SessionId,
    [ValidateSet('workshop-crash', 'database-crash', 'rabbitmq-crash', 'workshop-delay', 'workshop-crash-with-load')]
    [string[]]$ExperimentIds = @('workshop-crash', 'database-crash', 'workshop-delay', 'rabbitmq-crash')
)

$ErrorActionPreference = 'Stop'
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
$errorText = $null
$lock = $null
$mode = $(if ($RuleBased) { 'Rule-based; no AI used' } else { "AI: $Model" })
$catalog = Get-Content (Join-Path $PSScriptRoot 'experiments.json') -Raw | ConvertFrom-Json
$dependencies = Get-Content (Join-Path $PSScriptRoot 'dependencies.json') -Raw | ConvertFrom-Json
$registry = Get-ExperimentRegistry
$available = @($ExperimentIds | Select-Object -Unique)
New-Item -ItemType Directory -Path $output -Force | Out-Null

function Save-Progress {
    param([string]$Stage)
    $updatedUtc = [DateTime]::UtcNow.ToString('o')
    $events.Add([pscustomobject]@{ TimestampUtc = $updatedUtc; Stage = $Stage })
    $snapshot = [ordered]@{ RunId = $runId; StartedUtc = $startedUtc; UpdatedUtc = $updatedUtc; MaxExperiments = $MaxExperiments; BaselineSeconds = $BaselineSeconds; Events = @($events.ToArray()); Stage = $Stage; Mode = $mode; Execute = [bool]$Execute; Model = $(if (-not $RuleBased) { $Model } else { $null }); Rankings = @($rankings); Plans = @($plans.ToArray()); Experiments = @($completed.ToArray()); Error = $errorText }
    Write-AgentSnapshot -Path (Join-Path $output 'session.json') -Value $snapshot -Required
    Write-Host "Agent: $Stage"
}

try {
    $lock = [IO.File]::Open((Join-Path $PSScriptRoot 'agent.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
    if (Test-Path $stopPath) { throw 'STOP file exists; remove it before running.' }
    if (-not $RuleBased) {
        $models = Invoke-RestMethod 'http://localhost:11434/api/tags' -TimeoutSec 5
        if ($Model -notin @($models.models.name)) { throw "Model $Model is not installed. Run agent/setup-ai.ps1 or use -RuleBased explicitly." }
    }
    Save-Progress 'Collecting baseline'
    $baselinePath = & (Join-Path $PSScriptRoot 'baseline.ps1') -DurationSeconds $BaselineSeconds -OutputDirectory $output
    $baseline = Get-Content -LiteralPath $baselinePath -Raw | ConvertFrom-Json
    if (-not $baseline.Healthy) { throw 'Unhealthy baseline: no faults will be injected.' }
    if (-not $RuleBased) {
        Save-Progress 'Ranking experiments'
        $rankings = @(Get-AiExperimentRanking -Model $Model -Dependencies $dependencies -Baseline $baseline -Catalog @($catalog | Where-Object { $_.id -in $available }))
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

        $tool = $registry[$plan.id]
        $parameters = @{ TargetService = $tool.TargetService; FailureType = $tool.FailureType; DurationSeconds = [int]$plan.durationSeconds; RecoveryTimeoutSeconds = 120 }
        if ($tool.ConcurrentLoad) { $parameters.ConcurrentLoad = $true }
        $savedReport = $null
        Save-Progress "Executing $($plan.id)"
        try {
            & (Join-Path $scripts 'kill-service.ps1') @parameters -ProgressPath (Join-Path $output 'live-experiment.json') -ResultReportPath ([ref]$savedReport) | Out-Null
        }
        finally {
            if ($savedReport -and (Test-Path -LiteralPath $savedReport)) {
                Save-Progress "Analyzing $($plan.id)"
                $analysisParameters = @{ ReportPath = $savedReport }
                if (-not $RuleBased) { $analysisParameters.Model = $Model }
                $analysisPath = & (Join-Path $scripts 'analyze-anomalies.ps1') @analysisParameters
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
        if (-not $RuleBased -and $analysis.AiStatus -notlike 'Completed*') { throw 'AI analysis failed; evidence saved, remaining experiments aborted.' }
    }
    Save-Progress $(if ($Execute) { 'Completed' } else { 'Plans only; no faults injected' })
}
catch { $errorText = $_.Exception.Message; Save-Progress 'Stopped with error' }
finally {
    $lines = [System.Collections.Generic.List[string]]::new()
    $lines.Add('# Chaos Agent Findings')
    $lines.Add('')
    $lines.Add("Run: $runId. Mode: $mode. Execute: $Execute.")
    $lines.Add('')
    $lines.Add(("Error: $errorText").TrimEnd())
    $lines.Add('')
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
