[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateSet('Discovery', 'Planner', 'Injection', 'Detection', 'Recommendation')][string]$Role,
    [Parameter(Mandatory)][string]$RequestPath,
    [Parameter(Mandatory)][string]$ResponsePath
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'AgentTools.psm1') -Force
Import-Module (Join-Path $PSScriptRoot 'Telemetry.psm1') -Force
$scripts = Join-Path (Split-Path $PSScriptRoot -Parent) 'chaos-scripts'
$result = $null
$failure = $null
$reportPath = $null
try {
    $request = Get-Content -LiteralPath $RequestPath -Raw | ConvertFrom-Json
    switch ($Role) {
        Discovery {
            Import-Module (Join-Path $PSScriptRoot 'Discovery.psm1') -Force
            $result = Get-FailureDiscovery -Baseline $request.Baseline -Dependencies $request.Dependencies -Catalog @($request.Catalog) -Incidents @($request.Incidents)
        }
        Planner {
            $result = @(Get-AiExperimentRanking -Model $request.Model -Dependencies $request.Dependencies -Baseline $request.Baseline -Catalog @($request.Catalog) -Discovery $request.Discovery)
        }
        Injection {
            # Resolve tools locally; never execute targets or commands supplied by a model.
            Assert-ExperimentPlan -Plan $request.Plan -AvailableIds @($request.AvailableIds)
            $registry = Get-ExperimentRegistry
            $tool = $registry[$request.Plan.id]
            if (-not $tool) { throw 'No registered injection tool.' }
            $parameters = @{ TargetService = $tool.TargetService; FailureType = $tool.FailureType; DurationSeconds = [int]$request.Plan.durationSeconds; RecoveryTimeoutSeconds = 120 }
            if ($tool.ConcurrentLoad) { $parameters.ConcurrentLoad = $true }
            if ($tool.DelayMilliseconds) { $parameters.DelayMilliseconds = $tool.DelayMilliseconds }
            & (Join-Path $scripts 'kill-service.ps1') @parameters -ProgressPath $request.ProgressPath -ResultReportPath ([ref]$reportPath) | Out-Null
            $result = @{ ReportPath = $reportPath }
        }
        Detection {
            $analysisPath = & (Join-Path $scripts 'analyze-anomalies.ps1') -ReportPath $request.ReportPath -OutputName 'detection.json'
            $result = @{ AnalysisPath = $analysisPath }
        }
        Recommendation {
            $parameters = @{ ReportPath = $request.ReportPath; DetectionPath = $request.DetectionPath }
            if ($request.Model) { $parameters.Model = $request.Model }
            $analysisPath = & (Join-Path $scripts 'analyze-anomalies.ps1') @parameters
            $analysis = Get-Content -LiteralPath $analysisPath -Raw | ConvertFrom-Json
            $result = @{ AnalysisPath = $analysisPath }
            if ($request.Model -and $analysis.AiStatus -notlike 'Completed*') { throw "Recommendation failed: $($analysis.AiError)" }
        }
    }
} catch {
    $failure = $_.Exception.Message
    if ($Role -eq 'Injection') { $result = @{ ReportPath = $reportPath } }
} finally {
    Write-AgentSnapshot -Path $ResponsePath -Value @{ Role = $Role; ProcessId = $PID; Result = $result; Error = $failure; FinishedUtc = [DateTime]::UtcNow.ToString('o') } -Required
}
if ($failure) { exit 1 }
