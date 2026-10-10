[CmdletBinding()]
param([Parameter(Mandatory)][ValidatePattern('^\d{8}T\d{9}Z$')][string]$BeforeId,
      [Parameter(Mandatory)][ValidatePattern('^\d{8}T\d{9}Z$')][string]$AfterId)
$ErrorActionPreference='Stop'
$repo=Split-Path $PSScriptRoot -Parent
Import-Module (Join-Path $repo 'agent/Evidence.psm1') -Force
$before=Get-Content (Join-Path $repo "chaos-scripts/results/$BeforeId/report.json") -Raw | ConvertFrom-Json
$after=Get-Content (Join-Path $repo "chaos-scripts/results/$AfterId/report.json") -Raw | ConvertFrom-Json
$output=Join-Path $repo 'submission'
New-Item -ItemType Directory -Path $output -Force | Out-Null
Compare-ChaosReports $before $after | ConvertTo-Json -Depth 12 | Set-Content (Join-Path $output 'comparison.json') -Encoding UTF8
Write-Host 'Comparison saved to submission/comparison.json'
