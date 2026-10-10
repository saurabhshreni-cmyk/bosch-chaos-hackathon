[CmdletBinding()]
param([ValidateRange(7011,7099)][int]$Port=7015)
$ErrorActionPreference='Stop'
$repo=Split-Path $PSScriptRoot -Parent
$runId=[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
$project="pitstopday2-$($runId.ToLowerInvariant())"
$output=Join-Path $repo "submission/validation/$runId"
New-Item -ItemType Directory -Path $output -Force | Out-Null
function Invoke-DockerChecked {
    param([string[]]$Arguments)
    $value=& docker @Arguments
    if($LASTEXITCODE-ne 0){throw "Docker command failed: $($Arguments[0])"}
    return $value
}
$context=(Invoke-DockerChecked @('context','show') | Out-String).Trim()
$endpoint=(Invoke-DockerChecked @('context','inspect',$context,'--format','{{.Endpoints.docker.Host}}') | Out-String).Trim()
if($env:DOCKER_HOST -or $endpoint-notmatch '^npipe://'){throw 'Clean validation requires the local Windows Docker context.'}
$existing=@(Invoke-DockerChecked @('ps','-aq','--filter',"label=com.docker.compose.project=$project"))
if($existing.Count){throw 'Validation namespace already exists.'}
$configuration=(Invoke-DockerChecked @('compose','-f',(Join-Path $repo 'src/docker-compose.yml'),'config','--format','json') | Out-String) | ConvertFrom-Json
$configuration.name=$project
foreach($property in $configuration.services.PSObject.Properties){
    $service=$property.Value
    $service.PSObject.Properties.Remove('container_name')
    $service.PSObject.Properties.Remove('ports')
    if($property.Name-eq 'webapp'){
        $service | Add-Member -NotePropertyName ports -NotePropertyValue @([pscustomobject]@{target=7005;published="$Port";host_ip='127.0.0.1';protocol='tcp'})
    }
}
foreach($volume in $configuration.volumes.PSObject.Properties){$volume.Value.name="$($project)_$($volume.Name)"}
foreach($network in $configuration.networks.PSObject.Properties){$network.Value.name="$($project)_$($network.Name)"}
$compose=Join-Path $output 'compose.json'
$configuration | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath $compose -Encoding UTF8
$started=$false
$result=[ordered]@{RunId=$runId;Project=$project;Url="http://127.0.0.1:$Port";FreshVolumes=$true;OriginalDataUntouched=$true;StartedUtc=[DateTime]::UtcNow.ToString('o');Passed=$false;Services=@();Pages=@();Error=$null}
try{
    $started=$true
    Invoke-DockerChecked @('compose','-p',$project,'-f',$compose,'up','-d','--wait','--wait-timeout','240') | Out-Host
    $rows=(Invoke-DockerChecked @('compose','-p',$project,'-f',$compose,'ps','--all','--format','json') | Out-String).Trim()
    $result.Services=@($rows -split "`n" | Where-Object{$_} | ForEach-Object{$_ | ConvertFrom-Json} | Select-Object Service,State,Health,Image)
    if(@($result.Services | Where-Object{$_.State-ne 'running' -or $_.Health-eq 'unhealthy'}).Count){throw 'Fresh services are not running/healthy.'}
    foreach($module in @('CustomerManagement','VehicleManagement','WorkshopManagement')){
        $page=Invoke-WebRequest "$($result.Url)/$module" -UseBasicParsing -TimeoutSec 10
        $healthy=$page.StatusCode-eq 200 -and $page.Content-notmatch '(?i)module is offline|management\s*-\s*offline'
        $result.Pages+=@([pscustomobject]@{Module=$module;Healthy=$healthy})
        if(-not $healthy){throw "Fresh module offline: $module"}
    }
    $env:PITSTOP_URL=$result.Url
    & node (Join-Path $repo 'dashboard/workflow.mjs') (Join-Path $output 'workflow.json')
    if($LASTEXITCODE-ne 0){throw 'Fresh end-to-end workflow failed.'}
    $result.Passed=$true
}
catch{$result.Error=$_.Exception.Message;throw}
finally{
    $result.FinishedUtc=[DateTime]::UtcNow.ToString('o')
    $result | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $output 'result.json') -Encoding UTF8
    if($started){
        # Only this newly generated validation namespace is removed; never the user's project.
        if($project-notmatch '^pitstopday2-\d{8}t\d{9}z$'){throw 'Invalid cleanup namespace.'}
        Invoke-DockerChecked @('compose','-p',$project,'-f',$compose,'down','--volumes') | Out-Host
    }
    Write-Host "Clean validation: $output"
}
