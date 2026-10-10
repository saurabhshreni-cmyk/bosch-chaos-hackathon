$ErrorActionPreference = 'Stop'
Import-Module (Join-Path (Split-Path $PSScriptRoot -Parent) 'AgentTools.psm1') -Force
$ids = @('workshop-crash', 'database-crash', 'workshop-delay', 'rabbitmq-crash')
function Assert-Rejected {
    param($Plan, [string[]]$Available = $ids)
    $rejected = $false
    try { Assert-ExperimentPlan -Plan $Plan -AvailableIds $Available } catch { $rejected = $true }
    if (-not $rejected) { throw 'Unsafe plan was accepted.' }
}
Assert-ExperimentPlan -Plan ([pscustomobject]@{ id = 'database-crash'; durationSeconds = 20; reason = 'Shared dependency'; expectedImpact = 'Multiple modules unavailable' }) -AvailableIds $ids
Assert-Rejected ([pscustomobject]@{ id = 'unknown'; durationSeconds = 20; reason = 'x'; expectedImpact = 'x' })
Assert-Rejected ([pscustomobject]@{ id = 'database-crash'; durationSeconds = 61; reason = 'x'; expectedImpact = 'x' })
Assert-Rejected ([pscustomobject]@{ id = 'database-crash'; durationSeconds = 5.5; reason = 'x'; expectedImpact = 'x' })
Assert-Rejected ([pscustomobject]@{ id = 'database-crash'; durationSeconds = 20; reason = ''; expectedImpact = 'x' })
Assert-Rejected ([pscustomobject]@{ id = 'database-crash'; durationSeconds = 20; reason = ('x' * 241); expectedImpact = 'x' })
Assert-Rejected ([pscustomobject]@{ id = 'database-crash'; durationSeconds = 20; reason = 'x'; expectedImpact = 'x'; command = 'docker kill other-project' })
Assert-Rejected ([pscustomobject]@{ id = 'database-crash'; durationSeconds = 20; reason = 'x'; expectedImpact = 'x' }) -Available @('workshop-crash')
Write-Host 'Plan validation passed: targets, durations, extra commands, missing reasons, and repeated experiments rejected.'
