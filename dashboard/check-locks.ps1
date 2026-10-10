$repo = Split-Path $PSScriptRoot -Parent
$result = @{}
foreach ($item in @{ Agent = 'agent/agent.lock'; Experiment = 'chaos-scripts/experiment.lock' }.GetEnumerator()) {
    $path = Join-Path $repo $item.Value
    $handle = $null
    $busy = $false
    if (Test-Path -LiteralPath $path) {
        try { $handle = [IO.File]::Open($path, 'Open', 'ReadWrite', 'None') }
        catch { $busy = $true }
        finally { if ($handle) { $handle.Dispose() } }
    }
    $result[$item.Key] = $busy
}
$result | ConvertTo-Json -Compress
