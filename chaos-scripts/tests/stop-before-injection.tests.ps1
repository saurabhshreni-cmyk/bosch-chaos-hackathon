$ErrorActionPreference = 'Stop'
$temporary = Join-Path ([IO.Path]::GetTempPath()) ("pitstop-stop-test-" + [guid]::NewGuid().ToString('N'))
$scripts = Join-Path $temporary 'chaos-scripts'
$testState = @{ MutationAttempted = $false; ForeignContainer = $false }
New-Item -ItemType Directory -Path $scripts -Force | Out-Null
Copy-Item -LiteralPath (Join-Path (Split-Path $PSScriptRoot -Parent) 'kill-service.ps1') -Destination $scripts

function docker {
    $global:LASTEXITCODE = 0
    switch ($args[0]) {
        context { if ($args[1] -eq 'show') { 'test-local' } else { 'npipe://test' } }
        compose { 'test-container' }
        inspect {
            $labels = @{
                'com.docker.compose.project' = 'test'
                'com.docker.compose.service' = 'workshopmanagementapi'
                'com.docker.compose.project.config_files' = $(if ($testState.ForeignContainer) { Join-Path $temporary 'other/docker-compose.yml' } else { Join-Path $temporary 'src/docker-compose.yml' })
            }
            ConvertTo-Json -InputObject @(@{ Config = @{ Labels = $labels } }) -Depth 5 -Compress
        }
        default { $testState.MutationAttempted = $true; throw 'Unexpected Docker mutation.' }
    }
}
function Invoke-WebRequest {
    param($Uri, [switch]$UseBasicParsing, $TimeoutSec)
    $module = ($Uri -split '/')[-1]
    [pscustomobject]@{ StatusCode = 200; Content = ($module -replace 'Management', ' Management') }
}
function Start-Sleep {
    param($Seconds)
    New-Item -ItemType File -Path (Join-Path $scripts 'STOP') -Force | Out-Null
}

try {
    $failure = $null
    try { & (Join-Path $scripts 'kill-service.ps1') -BaselineRounds 1 | Out-Null }
    catch { $failure = $_.Exception.Message }
    if ($failure -notlike '*activated during baseline*' -or $testState.MutationAttempted) {
        throw "STOP guard failed: $failure"
    }
    Write-Host 'STOP during baseline prevents injection (Docker and HTTP mocked).'
    Remove-Item -LiteralPath (Join-Path $scripts 'STOP')
    $testState.ForeignContainer = $true
    $failure = $null
    try { & (Join-Path $scripts 'kill-service.ps1') -BaselineRounds 1 | Out-Null }
    catch { $failure = $_.Exception.Message }
    if ($failure -notlike '*not owned by this checkout*' -or $testState.MutationAttempted) {
        throw "Sandbox ownership guard failed: $failure"
    }
    Write-Host 'Container from another Compose configuration rejected before injection.'
}
finally {
    $resolved = [IO.Path]::GetFullPath($temporary)
    $tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
    if ($resolved.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase) -and (Split-Path $resolved -Leaf) -like 'pitstop-stop-test-*') {
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}
