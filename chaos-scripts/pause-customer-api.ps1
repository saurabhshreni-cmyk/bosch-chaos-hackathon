<# Pauses the Customer API process without restarting it. Dry run unless -Execute. #>
[CmdletBinding()]
param(
    [ValidateRange(5,60)][int]$DurationSeconds = 15,
    [ValidateRange(1,10)][int]$RequestTimeoutSeconds = 3,
    [ValidateRange(1,10)][int]$BaselineRounds = 3,
    [ValidateRange(1,30000)][int]$MaxUnaffectedLatencyMs = 3000,
    [ValidateRange(10,180)][int]$RecoveryTimeoutSeconds = 90,
    [switch]$Execute
)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'PauseExperiment.ps1') -Service customermanagementapi @PSBoundParameters
