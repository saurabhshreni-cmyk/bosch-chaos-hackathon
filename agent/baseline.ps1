[CmdletBinding()]
param(
    [ValidateRange(3, 600)][int]$DurationSeconds = 180,
    [ValidateRange(1, 10)][int]$IntervalSeconds = 2,
    [string]$OutputDirectory = (Join-Path $PSScriptRoot 'runs/baseline')
)
$ErrorActionPreference = 'Stop'
$lock = [IO.File]::Open((Join-Path (Split-Path $PSScriptRoot -Parent) 'chaos-scripts/experiment.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
try {
$samples = [System.Collections.Generic.List[object]]::new()
$timer = [Diagnostics.Stopwatch]::StartNew()
while ($timer.Elapsed.TotalSeconds -lt $DurationSeconds) {
    if (Test-Path (Join-Path (Split-Path $PSScriptRoot -Parent) 'chaos-scripts/STOP')) { throw 'Baseline cancelled by STOP file.' }
    foreach ($module in @('CustomerManagement', 'VehicleManagement', 'WorkshopManagement')) {
        $clock = [Diagnostics.Stopwatch]::StartNew()
        $healthy = $false; $status = $null; $offline = $false
        try {
            $response = Invoke-WebRequest "http://localhost:7005/$module" -UseBasicParsing -TimeoutSec 5
            $status = [int]$response.StatusCode
            $offline = $response.Content -match '(?i)module is offline|management\s*-\s*offline'
            $healthy = $status -eq 200 -and -not $offline -and $response.Content -match ($module -replace 'Management', ' Management')
        }
        catch { Write-Warning "Baseline request failed: $module" }
        $clock.Stop()
        $samples.Add([pscustomobject]@{ TimestampUtc = [DateTime]::UtcNow.ToString('o'); Module = $module; Phase = 'baseline'; Healthy = $healthy; StatusCode = $status; OfflinePage = $offline; LatencyMs = [math]::Round($clock.Elapsed.TotalMilliseconds, 2) })
    }
    Start-Sleep -Seconds $IntervalSeconds
}
$summary = foreach ($module in @('CustomerManagement', 'VehicleManagement', 'WorkshopManagement')) {
    $rows = @($samples | Where-Object Module -eq $module)
    $latencies = @($rows.LatencyMs | Sort-Object)
    $failures = @($rows | Where-Object { -not $_.Healthy }).Count
    $lower = [int][math]::Floor(($rows.Count - 1) / 2)
    $upper = [int][math]::Floor($rows.Count / 2)
    [pscustomobject]@{ Module = $module; Samples = $rows.Count; Failures = $failures; ErrorRate = $failures / $rows.Count; MedianMs = ($latencies[$lower] + $latencies[$upper]) / 2; P95Ms = $latencies[[int][math]::Ceiling($rows.Count * 0.95) - 1] }
}
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$result = [ordered]@{ DurationSeconds = $timer.Elapsed.TotalSeconds; Healthy = @($samples | Where-Object { -not $_.Healthy }).Count -eq 0; ModuleStats = @($summary); Samples = @($samples.ToArray()); Limitations = 'Sequential fixed-interval read probes; not a production load test.' }
$path = Join-Path $OutputDirectory 'baseline.json'
$result | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $path -Encoding UTF8
$samples | Export-Csv (Join-Path $OutputDirectory 'baseline.csv') -NoTypeInformation
Write-Host "Baseline complete: $path"
Write-Output $path
}
finally { $lock.Dispose() }
