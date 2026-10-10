<# Starts the existing console with local tooling and an optional ignored Groq .env.
No model requests or chaos experiments are started by this launcher. #>
[CmdletBinding()]
param([ValidateRange(1024,65535)][int]$Port = 5280)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$workspace = Split-Path $repo -Parent
$runtime = Join-Path $workspace '.runtime'
$dotnet = Get-Command dotnet -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
$dotnetPath = if ($dotnet) { $dotnet.Source } else { Join-Path $runtime 'dotnet/dotnet.exe' }
if (-not (Test-Path -LiteralPath $dotnetPath)) { throw 'Install the .NET 10 SDK or put dotnet on PATH.' }
foreach ($directory in @(
    (Join-Path $runtime 'pwsh'),
    (Join-Path $env:LOCALAPPDATA 'Programs/DockerDesktop/resources/bin')
)) {
    if (Test-Path -LiteralPath $directory) { $env:PATH = $directory + [IO.Path]::PathSeparator + $env:PATH }
}
if (-not $env:GROQ_API_KEY) {
    $envFile = Join-Path $repo 'agentic-chaos/.env'
    if (Test-Path -LiteralPath $envFile) {
        foreach ($line in Get-Content -LiteralPath $envFile) {
            if ($line -match '^\s*GROQ_API_KEY\s*=\s*(.+?)\s*$') {
                $value = $Matches[1].Trim().Trim([char]34, [char]39)
                if ($value -and -not $value.StartsWith('#')) { $env:GROQ_API_KEY = $value }
                break
            }
        }
    }
}
Write-Host "Console: http://127.0.0.1:$Port"
Write-Host "Groq key configured: $([bool]$env:GROQ_API_KEY)"
& $dotnetPath run --project (Join-Path $PSScriptRoot 'Dashboard.csproj') --urls "http://127.0.0.1:$Port"
if ($LASTEXITCODE -ne 0) { throw "Dashboard exited with code $LASTEXITCODE." }
