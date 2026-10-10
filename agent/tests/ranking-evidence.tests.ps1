$ErrorActionPreference = 'Stop'
Import-Module (Join-Path (Split-Path $PSScriptRoot -Parent) 'AgentTools.psm1') -Force
Import-Module (Join-Path (Split-Path $PSScriptRoot -Parent) 'Evidence.psm1') -Force
$plans = @(
    [pscustomobject]@{id='database-crash';durationSeconds=20;reason='Shared SQL blast radius.';expectedImpact='All read modules may fail.'},
    [pscustomobject]@{id='workshop-crash';durationSeconds=20;reason='Test module isolation.';expectedImpact='Only Workshop should fail.'}
)
Assert-ExperimentRanking -Ranking ([pscustomobject]@{rankings=$plans}) -AvailableIds @('workshop-crash','database-crash')
foreach($invalid in @(
    [pscustomobject]@{rankings=@($plans[0],$plans[0])},
    [pscustomobject]@{rankings=@($plans[0])},
    [pscustomobject]@{rankings=$plans;command='anything'}
)){
    $rejected=$false
    try{Assert-ExperimentRanking $invalid @('workshop-crash','database-crash')}catch{$rejected=$true}
    if(-not $rejected){throw 'Invalid ranking accepted.'}
}
$samples=@(
    [pscustomobject]@{Module='WorkshopManagement';Phase='baseline';Healthy=$true;LatencyMs=20},
    [pscustomobject]@{Module='WorkshopManagement';Phase='fault';Healthy=$true;LatencyMs=30}
)
$report=[pscustomobject]@{RunId='test';Samples=$samples;Recovered=$true;RecoverySeconds=0;TargetService='workshopmanagementapi';FailureType='NetworkDelay';DelayMilliseconds=500;RequestedDurationSeconds=20}
if((Get-ProbeScore $report).Value-ne 100){throw 'Healthy score incorrect.'}
$report.RecoverySeconds=60
if((Get-ProbeScore $report).Value-ne 85){throw 'Fractional recovery must not round to an integer component.'}
$report.RecoverySeconds=16.98
if((Get-ProbeScore $report).Value-ne 95.8){throw 'Measured decimal recovery score incorrect.'}
$comparison=Compare-ChaosReports $report $report
if($comparison.BeforeScore.Value-ne 95.8){throw 'Comparison must use measured recovery.'}
$other=$report.PSObject.Copy()
$other.DelayMilliseconds=1000
$rejected=$false
try{Compare-ChaosReports $report $other}catch{$rejected=$true}
if(-not $rejected){throw 'Unmatched comparison was accepted.'}
$report.RecoverySeconds=0
$report.Recovered=$false
if((Get-ProbeScore $report).Value-ne 70){throw 'Unverified recovery incorrectly scored.'}
$report.Samples[1].Healthy=$false
if((Get-ProbeScore $report).Value-ne 0){throw 'Failed sample incorrectly scored.'}
$report.Samples=@($samples[0])
if($null-ne (Get-ProbeScore $report).Value){throw 'No-fault run got a score.'}
Write-Host 'PASS: complete unique rankings, command rejection, measured score, and missing-evidence guards.'
