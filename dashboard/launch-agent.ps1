param(
    [ValidateSet('detect', 'preview', 'execute')][string]$Mode,
    [ValidateSet('ai', 'rules')][string]$Engine,
    [ValidateRange(1, 4)][int]$Budget,
    [ValidateRange(3, 600)][int]$Baseline,
    [ValidatePattern('^[a-zA-Z0-9][a-zA-Z0-9._:/-]*$')][string]$Model,
    [ValidatePattern('^\d{8}T\d{9}Z$')][string]$SessionId,
    [string]$Experiments,
    [switch]$AutoDiscover
)
$ErrorActionPreference = 'Stop'
$ids = @($Experiments -split ',' | Where-Object { $_ })
foreach ($id in $ids) {
    if ($id -notin @('workshop-crash', 'database-crash', 'rabbitmq-crash', 'workshop-delay', 'workshop-delay-high', 'workshop-crash-with-load')) { throw 'Unknown experiment.' }
}
$parameters = @{ Model = $Model; MaxExperiments = $Budget; BaselineSeconds = $Baseline; ExperimentIds = $ids; SessionId = $SessionId }
if ($Mode -eq 'execute') { $parameters.Execute = $true }
if ($Engine -eq 'rules') { $parameters.RuleBased = $true }
if ($AutoDiscover) { $parameters.AutoDiscover = $true }
if ($Mode -eq 'detect') { $parameters.DetectOnly = $true }
& (Join-Path (Split-Path $PSScriptRoot -Parent) 'agent/run-agent.ps1') @parameters
