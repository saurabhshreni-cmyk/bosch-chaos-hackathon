[CmdletBinding()]
param([Parameter(Mandatory)][ValidatePattern('^\d{8}T\d{9}Z$')][string]$SessionId)
$ErrorActionPreference='Stop'
$repo=Split-Path $PSScriptRoot -Parent
Import-Module (Join-Path $repo 'agent/Evidence.psm1') -Force
$folder=Join-Path $repo "agent/runs/$SessionId"
$session=Get-Content (Join-Path $folder 'session.json') -Raw | ConvertFrom-Json
if($session.Stage-ne 'Completed'){throw 'Only completed sessions can have derived scores refreshed.'}
foreach($entry in $session.Experiments){
    if($entry.RunId-notmatch '^\d{8}T\d{9}Z$'){throw 'Invalid evidence ID.'}
    $report=Get-Content (Join-Path $repo "chaos-scripts/results/$($entry.RunId)/report.json") -Raw | ConvertFrom-Json
    $entry | Add-Member -NotePropertyName ProbeScore -NotePropertyValue (Get-ProbeScore $report) -Force
}
$session | Add-Member -NotePropertyName ScoreRecomputedUtc -NotePropertyValue ([DateTime]::UtcNow.ToString('o')) -Force
$session | ConvertTo-Json -Depth 12 | Set-Content (Join-Path $folder 'session.json') -Encoding UTF8
$entry=$null
$lines=Get-Content (Join-Path $folder 'findings.md') | ForEach-Object {
    if($_-match '^## (.+)$'){$id=$Matches[1];$entry=@($session.Experiments | Where-Object ExperimentId -eq $id)[0]}
    if($_-like 'Read-probe heuristic score:*' -and $entry){"Read-probe heuristic score: $($entry.ProbeScore.Value)/100. $($entry.ProbeScore.Method)"}else{$_}
}
$lines | Set-Content (Join-Path $folder 'findings.md') -Encoding UTF8
Write-Host 'Derived scores refreshed from unchanged raw measurements.'
