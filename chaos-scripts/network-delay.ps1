[CmdletBinding()]
param(
    [ValidateRange(1, 60)][int]$DurationSeconds = 30,
    [ValidateRange(100, 1000)][int]$DelayMilliseconds = 500
)
$ErrorActionPreference = 'Stop'
$report = & (Join-Path $PSScriptRoot 'kill-service.ps1') -FailureType NetworkDelay -DurationSeconds $DurationSeconds -DelayMilliseconds $DelayMilliseconds
& (Join-Path $PSScriptRoot 'analyze-anomalies.ps1') -ReportPath $report
