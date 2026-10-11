$ErrorActionPreference = 'Stop'
$worker = Join-Path (Split-Path $PSScriptRoot -Parent) 'worker.ps1'
$directory = Join-Path ([IO.Path]::GetTempPath()) ('pitstop-workers-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $directory | Out-Null
$requestPath = Join-Path $directory 'request.json'
$responsePath = Join-Path $directory 'response.json'
$reportPath = Join-Path $directory 'report.json'
function Invoke-TestWorker {
    param([string]$Role, $Request)
    $Request | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $requestPath -Encoding UTF8
    & (Join-Path $PSHOME 'powershell.exe') -NoProfile -ExecutionPolicy Bypass -File $worker -Role $Role -RequestPath $requestPath -ResponsePath $responsePath | Out-Host
    return Get-Content -LiteralPath $responsePath -Raw | ConvertFrom-Json
}
try {
    @{ RunId = 'fixture'; TargetService = 'sqlserver'; Recovered = $true; RecoverySeconds = 2; Samples = @(
        @{ Phase = 'baseline'; Module = 'VehicleManagement'; Healthy = $true; LatencyMs = 100 },
        @{ Phase = 'fault'; Module = 'VehicleManagement'; Healthy = $false; LatencyMs = 5000; StatusCode = $null }
    ) } | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportPath -Encoding UTF8
    $detector = Invoke-TestWorker Detection @{ ReportPath = $reportPath }
    if ($detector.Error -or $detector.ProcessId -eq $PID) { throw 'Detector did not run successfully in an isolated process.' }
    $detectionPath = $detector.Result.AnalysisPath
    $before = Get-Content -LiteralPath $detectionPath -Raw
    $recommendation = Invoke-TestWorker Recommendation @{ ReportPath = $reportPath; DetectionPath = $detectionPath }
    if ($recommendation.Error -or $recommendation.ProcessId -eq $detector.ProcessId) { throw 'Recommendation worker did not execute independently.' }
    $analysis = Get-Content -LiteralPath $recommendation.Result.AnalysisPath -Raw | ConvertFrom-Json
    if ($analysis.Anomalies.Count -ne 1 -or $analysis.AiStatus -ne 'Not configured') { throw 'Detector handoff changed evidence or claimed AI without a model.' }
    if ((Get-Content -LiteralPath $detectionPath -Raw) -ne $before) { throw 'Recommendation worker mutated detector evidence.' }
    $invalid = Invoke-TestWorker Injection @{ Plan = @{ id = 'outside-sandbox'; durationSeconds = 5; reason = 'Invalid'; expectedImpact = 'Rejected' }; AvailableIds = @('workshop-crash') }
    if (-not $invalid.Error -or $invalid.Result.ReportPath) { throw 'Injection worker accepted an unregistered plan.' }
    $tooLong = Invoke-TestWorker Injection @{ Plan = @{ id = 'workshop-delay-high'; durationSeconds = 21; reason = 'Boundary'; expectedImpact = 'Rejected' }; AvailableIds = @('workshop-delay-high') }
    if (-not $tooLong.Error) { throw 'Stronger delay exceeded its code-owned duration limit.' }
    $wrong = Get-Content -LiteralPath $detectionPath -Raw | ConvertFrom-Json
    $wrong.RunId = 'other-run'
    $wrong | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $detectionPath -Encoding UTF8
    $mismatch = Invoke-TestWorker Recommendation @{ ReportPath = $reportPath; DetectionPath = $detectionPath }
    if (-not $mismatch.Error) { throw 'Recommendation worker accepted mismatched evidence.' }
    Write-Host 'Worker tests passed: isolated processes, evidence handoff, no-model honesty, unsafe-plan rejection and mismatch rejection. No faults injected.'
} finally {
    $resolved = [IO.Path]::GetFullPath($directory)
    $tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    if (-not $resolved.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'Refusing to clean outside the temporary directory.' }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
