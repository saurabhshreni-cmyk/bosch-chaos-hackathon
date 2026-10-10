[CmdletBinding()]
param([ValidateRange(1, 60)][int]$DurationSeconds = 60)
$ErrorActionPreference = 'Stop'
$report = & (Join-Path $PSScriptRoot 'kill-service.ps1') -TargetService rabbitmq -DurationSeconds $DurationSeconds -RecoveryTimeoutSeconds 120
& (Join-Path $PSScriptRoot 'analyze-anomalies.ps1') -ReportPath $report
