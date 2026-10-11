$ErrorActionPreference = 'Stop'
Import-Module (Join-Path (Split-Path $PSScriptRoot -Parent) 'Discovery.psm1') -Force
$directory = Split-Path $PSScriptRoot -Parent
$catalog = Get-Content (Join-Path $directory 'experiments.json') -Raw | ConvertFrom-Json
$dependencies = Get-Content (Join-Path $directory 'dependencies.json') -Raw | ConvertFrom-Json
$baseline = [pscustomobject]@{ Healthy = $true; ModuleStats = @([pscustomobject]@{ Module = 'WorkshopManagement'; Failures = 0; MedianMs = 100; P95Ms = 900 }) }
$recent = [pscustomobject]@{ subject = 'WorkshopManagement'; kind = 'Latency regression'; detected = [DateTime]::UtcNow.AddMinutes(-2).ToString('o'); status = 'Recovered' }
$result = Get-FailureDiscovery -Baseline $baseline -Dependencies $dependencies -Catalog $catalog -Incidents @($recent)
if ($result.Candidates[0].Id -notlike 'workshop-delay*') { throw 'Observed latency did not prioritize a registered latency experiment.' }
if (@($result.Findings | Where-Object Type -eq 'Observed slowdown').Count -ne 1) { throw 'Measured slowdown missing.' }
if (@($result.Findings | Where-Object Type -eq 'Potential risk').Count -ne 2) { throw 'Shared dependencies not mapped.' }
if (@($result.ProposedTests | Where-Object Executable).Count -ne 0) { throw 'Unimplemented scenarios must not be executable.' }
$baseline.Healthy = $false; $baseline.ModuleStats[0].Failures = 1
$blocked = Get-FailureDiscovery -Baseline $baseline -Dependencies $dependencies -Catalog $catalog -Incidents @()
if ($blocked.HealthyBaseline -or @($blocked.Findings | Where-Object Type -eq 'Observed failure').Count -ne 1) { throw 'Current unhealthy baseline was not reported.' }
$old = [pscustomobject]@{ subject = 'sqlserver'; kind = 'Container health failure'; detected = [DateTime]::UtcNow.AddDays(-3).ToString('o'); status = 'Active' }
$ignored = Get-FailureDiscovery -Baseline $baseline -Dependencies $dependencies -Catalog @($catalog | Where-Object id -eq 'workshop-delay') -Incidents @($old)
if (@($ignored.Findings | Where-Object Type -eq 'Recorded incident').Count -ne 0 -or $ignored.Candidates.Count -ne 1) { throw 'Old history or disabled experiments leaked into discovery.' }
Write-Host 'Discovery tests passed: measurements, historical evidence, shared risks, allowed candidates and proposal safety.'
$independent = Get-FailureDiscovery -Baseline $baseline -Dependencies $dependencies -Catalog @() -Incidents @()
if (@($independent.Candidates).Count -ne 0 -or @($independent.Findings | Where-Object Type -eq 'Observed failure').Count -ne 1) { throw 'Detection must report failures without an experiment catalog.' }
Write-Host 'Catalog-independent detection passed.'
