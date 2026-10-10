function Write-AgentSnapshot {
    param([string]$Path, $Value, [switch]$Required)
    if (-not $Path) { return }
    $temporary = "$Path.tmp"
    try {
        New-Item -ItemType Directory -Path (Split-Path $Path -Parent) -Force | Out-Null
        $Value | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $temporary -Encoding UTF8
        for ($attempt=0; $attempt-lt 8; $attempt++) {
            try {
                if ([IO.File]::Exists($Path)) { [IO.File]::Replace($temporary, $Path, [NullString]::Value) }
                else { [IO.File]::Move($temporary, $Path) }
                break
            }
            catch {
                if ($attempt-eq 7) { throw }
                Start-Sleep -Milliseconds 100
            }
        }
    }
    catch { if ($Required) { throw }; Write-Warning "Live snapshot unavailable: $($_.Exception.Message)" }
}
Export-ModuleMember -Function Write-AgentSnapshot
