[CmdletBinding()]
param([ValidatePattern('^[a-zA-Z0-9._:/-]+$')][string]$Model = 'qwen2.5:1.5b')
$ErrorActionPreference = 'Stop'
$compose = Join-Path $PSScriptRoot 'compose.ai.yml'
& docker compose -f $compose up -d
if ($LASTEXITCODE -ne 0) { throw 'Could not start local Ollama.' }
$ready = $false
for ($attempt = 0; $attempt -lt 15; $attempt++) {
    try { Invoke-RestMethod 'http://localhost:11434/api/tags' -TimeoutSec 2 | Out-Null; $ready = $true; break }
    catch { Start-Sleep -Seconds 2 }
}
if (-not $ready) { throw 'Ollama did not become ready; check the AI container logs.' }
& docker compose -f $compose exec -T ollama ollama pull $Model
if ($LASTEXITCODE -ne 0) { throw 'Model download failed.' }
Write-Host "Local AI ready: $Model at http://localhost:11434"
