[CmdletBinding()]
param([switch]$ReuseBuiltTests)
$ErrorActionPreference='Stop'
$repo=Split-Path $PSScriptRoot -Parent
$checks=[System.Collections.Generic.List[object]]::new()
$passed=$false
$failure=$null
Push-Location $repo
try{
    foreach($test in @(Get-ChildItem 'agent/tests/*.tests.ps1','chaos-scripts/tests/*.tests.ps1')){
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $test.FullName
        if($LASTEXITCODE-ne 0){throw "Failed: $($test.Name)"}
        $checks.Add([pscustomobject]@{Check=$test.Name;Passed=$true;Kind='Mocked/unit'})
    }
    Push-Location (Join-Path $repo 'dashboard')
    try{
        & npm.cmd test
        if($LASTEXITCODE-ne 0){throw 'Dashboard API tests failed.'}
        $checks.Add([pscustomobject]@{Check='Dashboard API, automatic monitor and retained evidence';Passed=$true;Kind='Unit/API'})
        & npm.cmd run test:browser
        if($LASTEXITCODE-ne 0){throw 'Dashboard browser tests failed.'}
        $checks.Add([pscustomobject]@{Check='Desktop/mobile, automatic incidents, 3D topology and empty-history browser tests';Passed=$true;Kind=$(if($env:RUN_AGENT_TEST-eq '1'){'Browser including real preview'}else{'Browser; optional real preview test skipped'})})
        & npm.cmd audit
        if($LASTEXITCODE-ne 0){throw 'Dashboard dependency audit failed.'}
        $checks.Add([pscustomobject]@{Check='Dashboard npm audit';Passed=$true;Kind='Dependency audit'})
    }finally{Pop-Location}
    if($ReuseBuiltTests){
        & docker run --rm --mount "type=bind,source=$repo/src,target=/workspace" -w /workspace pitstop-dotnet-sdk-base:1.0 dotnet WebApp.ResilienceTests/bin/Debug/net10.0/WebApp.ResilienceTests.dll
    }else{
        & docker run --rm --mount "type=bind,source=$repo/src,target=/workspace" -w /workspace pitstop-dotnet-sdk-base:1.0 dotnet run --project WebApp.ResilienceTests/WebApp.ResilienceTests.csproj
    }
    if($LASTEXITCODE-ne 0){throw 'Resilience tests failed.'}
    $checks.Add([pscustomobject]@{Check='Healthy result, one write attempt and timeout fallback';Passed=$true;Kind=$(if($ReuseBuiltTests){'.NET console regression; reuse binaries compiled earlier this session'}else{'.NET compiled console regression'})})
    & node dashboard/verify-submission.mjs
    if($LASTEXITCODE-ne 0){throw 'Submission media validation failed.'}
    $checks.Add([pscustomobject]@{Check='Five deliverables, video playback and one-page PDF';Passed=$true;Kind='Real artifact verification'})
    $passed=$true
}catch{$failure=$_.Exception.Message;throw}
finally{
    try{
        [ordered]@{Passed=$passed;VerifiedUtc=[DateTime]::UtcNow.ToString('o');Error=$failure;Checks=@($checks.ToArray());Limitations='Legacy transitive NuGet vulnerability warnings remain. No production safety, write-fault durability, model-quality or portal submission certification.'} | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $repo 'submission/verification.json') -Encoding UTF8
    }finally{Pop-Location}
}
