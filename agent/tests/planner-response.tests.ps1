$ErrorActionPreference = 'Stop'
$module = Import-Module (Join-Path (Split-Path $PSScriptRoot -Parent) 'AgentTools.psm1') -Force -PassThru
$catalog = @([pscustomobject]@{ id = 'workshop-delay'; defaultDurationSeconds = 20 })
$valid = '{"id":"workshop-delay","durationSeconds":20,"reason":"Test Workshop latency isolation.","expectedImpact":"Workshop slows; Customer and Vehicle should remain available."}'

# Inject only the HTTP response inside the module; parsing and validation remain real.
& $module {
    function script:Invoke-RestMethod {
        param($Uri, $Method, $ContentType, $Body, $TimeoutSec)
        $request = $Body | ConvertFrom-Json
        if ($request.format.properties.reason.maxLength -ne 240) { throw 'Missing schema length bound.' }
        $index = $script:plannerTest.Index
        $script:plannerTest.Index++
        if ($index -ge $script:plannerTest.Responses.Count) { throw 'Unexpected additional model request.' }
        return $script:plannerTest.Responses[$index]
    }
}

function Test-Response {
    param([object[]]$Responses, [int]$ExpectedCalls, [bool]$ShouldPass)
    $state = @{ Responses = $Responses; Index = 0 }
    & $module { param($State) $script:plannerTest = $State } $state
    $passed = $false
    try {
        $plan = Get-AiExperimentPlan -Model mock -Dependencies @{} -Baseline @{} -Catalog $catalog -PreviousRuns @() -WarningAction SilentlyContinue
        $passed = $plan.id -eq 'workshop-delay'
    }
    catch { if ($ShouldPass) { throw } }
    if ($passed -ne $ShouldPass -or $state.Index -ne $ExpectedCalls) { throw 'Unexpected planner result or retry count.' }
}

$complete = @{ done_reason = 'stop'; message = @{ content = $valid } }
$truncated = @{ done_reason = 'length'; message = @{ content = '{"reason":"unfinished' } }
Test-Response -Responses @($complete) -ExpectedCalls 1 -ShouldPass $true
Test-Response -Responses @($truncated, $complete) -ExpectedCalls 2 -ShouldPass $true
Test-Response -Responses @(@{ message = @{ content = 'invalid json' } }, $complete) -ExpectedCalls 2 -ShouldPass $true
Test-Response -Responses @($truncated, $truncated) -ExpectedCalls 2 -ShouldPass $false
Test-Response -Responses @(@{ message = @{ content = ($valid -replace 'workshop-delay', 'unknown') } }) -ExpectedCalls 1 -ShouldPass $false
Write-Host 'Planner response tests passed: bounded retry, incomplete JSON, and unsafe-plan rejection (HTTP mocked).'
