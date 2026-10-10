[CmdletBinding()]
param(
    [ValidateRange(1, 60)][int]$DurationSeconds = 30,
    [ValidateRange(1, 3)][int]$MaxImpactedModules = 2,
    [ValidateRange(1, 10)][int]$BaselineRounds = 3,
    [ValidateRange(10, 180)][int]$RecoveryTimeoutSeconds = 120,
    [string]$Model
)

$ErrorActionPreference = 'Stop'
Write-Host 'SQL Server outage: all three modules share this database server.'
Write-Host 'Only the SQL Server container is killed; its persistent volume is retained.'
$savedReport = $null
try {
    & (Join-Path $PSScriptRoot 'kill-service.ps1') `
        -TargetService sqlserver -DurationSeconds $DurationSeconds `
        -MaxImpactedModules $MaxImpactedModules -BaselineRounds $BaselineRounds `
        -RecoveryTimeoutSeconds $RecoveryTimeoutSeconds -ResultReportPath ([ref]$savedReport) | Out-Null
}
finally {
    if ($savedReport -and (Test-Path -LiteralPath $savedReport)) {
        & (Join-Path $PSScriptRoot 'analyze-anomalies.ps1') -ReportPath $savedReport -Model $Model
    }
}
