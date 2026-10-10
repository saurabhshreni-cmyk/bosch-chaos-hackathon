$ErrorActionPreference = 'Stop'
$analyzer = Join-Path (Split-Path $PSScriptRoot -Parent) 'analyze-anomalies.ps1'
$testDir = Join-Path ([System.IO.Path]::GetTempPath()) ("pitstop-anomaly-test-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testDir | Out-Null
$reportPath = Join-Path $testDir 'report.json'
$analysisPath = Join-Path $testDir 'anomalies.json'

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

try {
    $samples = @(
        @{ Phase = 'baseline'; Module = 'VehicleManagement'; Healthy = $true; LatencyMs = 100 },
        @{ Phase = 'baseline'; Module = 'VehicleManagement'; Healthy = $true; LatencyMs = 100 },
        @{ Phase = 'baseline'; Module = 'VehicleManagement'; Healthy = $true; LatencyMs = 100 },
        @{ Phase = 'fault'; Module = 'VehicleManagement'; Healthy = $true; LatencyMs = 110; StatusCode = 200 },
        @{ Phase = 'fault'; Module = 'VehicleManagement'; Healthy = $true; LatencyMs = 500; StatusCode = 200 },
        @{ Phase = 'fault'; Module = 'VehicleManagement'; Healthy = $false; LatencyMs = 5000; StatusCode = $null },
        @{ Phase = 'recovery'; Module = 'VehicleManagement'; Healthy = $false; LatencyMs = 80; StatusCode = 200; OfflinePage = $true },
        @{ Phase = 'recovery'; Module = 'VehicleManagement'; Healthy = $true; LatencyMs = 100; StatusCode = 200 }
    )
    @{ RunId = 'fixture'; TargetService = 'sqlserver'; Recovered = $true; RecoverySeconds = 2; Samples = $samples } |
        ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $reportPath -Encoding UTF8
    & $analyzer -ReportPath $reportPath | Out-Null
    $analysis = Get-Content -LiteralPath $analysisPath -Raw | ConvertFrom-Json
    Assert-True ($analysis.Anomalies.Count -eq 3) 'Expected one slowdown, one timeout, and one HTTP 200 fallback.'
    Assert-True (@($analysis.Anomalies | Where-Object Kind -eq 'Availability failure').Count -eq 2) 'Availability failures misclassified.'
    Assert-True ($analysis.ModuleStats[0].LatencyThresholdMs -eq 350) 'Latency threshold must handle zero baseline MAD.'
    Assert-True ($analysis.AiStatus -eq 'Not configured') 'No-model mode must not claim AI results.'

    # Mock only the model API; the actual analyzer and JSON validation run.
    function Invoke-RestMethod {
        param($Uri, $Method, $ContentType, $Body, $TimeoutSec)
        $request = $Body | ConvertFrom-Json
        Assert-True ($Uri -eq 'http://localhost:11434/api/chat') 'Unexpected model endpoint.'
        Assert-True (-not $request.stream -and $request.format.type -eq 'object') 'Expected structured non-streaming request.'
        return @{ model = 'mock'; message = @{ content = '{"findings":[{"severity":"high","title":"Unavailable","evidenceIds":["E2"],"explanation":"Probe failed","recommendedFix":"Investigate retries","confidence":"medium"}]}' } }
    }
    & $analyzer -ReportPath $reportPath -Model mock | Out-Null
    $analysis = Get-Content -LiteralPath $analysisPath -Raw | ConvertFrom-Json
    Assert-True ($analysis.AiStatus -like 'Completed*') 'Valid AI findings should be retained.'

    function Invoke-RestMethod {
        return @{ model = 'mock'; message = @{ content = '{"findings":[{"severity":"high","title":"Unsupported","evidenceIds":["E999"],"explanation":"Unknown evidence","recommendedFix":"Investigate","confidence":"low"}]}' } }
    }
    & $analyzer -ReportPath $reportPath -Model mock -WarningAction SilentlyContinue | Out-Null
    $analysis = Get-Content -LiteralPath $analysisPath -Raw | ConvertFrom-Json
    Assert-True ($analysis.AiStatus -like 'Failed*' -and $analysis.Anomalies.Count -eq 3) 'Invalid AI references must fail while retaining measured evidence.'
    Write-Host 'Anomaly analysis tests passed (model responses mocked; no real inference).'
}
finally {
    Remove-Item -LiteralPath $reportPath, $analysisPath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $testDir -Force
}
