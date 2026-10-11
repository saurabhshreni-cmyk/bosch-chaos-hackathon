function Get-FailureDiscovery {
    param($Baseline, $Dependencies, $Catalog, [object[]]$Incidents = @())
    $findings = [System.Collections.Generic.List[object]]::new()
    $priority = @{}
    foreach ($entry in $Catalog) { $priority[$entry.id] = 0 }
    foreach ($row in $Baseline.ModuleStats) {
        if ($row.Failures -gt 0) {
            $findings.Add([pscustomobject]@{ Type = 'Observed failure'; Subject = $row.Module; Summary = "$($row.Failures) baseline probes failed. Restore health before chaos testing."; Source = 'Current baseline' })
        } elseif ($row.P95Ms -gt [math]::Max(500, $row.MedianMs * 3)) {
            $findings.Add([pscustomobject]@{ Type = 'Observed slowdown'; Subject = $row.Module; Summary = "p95 $($row.P95Ms) ms exceeds the baseline review threshold. This does not establish root cause."; Source = 'Current baseline' })
            if ($row.Module -eq 'WorkshopManagement') {
                foreach ($entry in @($Catalog | Where-Object failureType -eq 'NetworkDelay')) { $priority[$entry.id] += 30 }
            }
        }
    }
    $cutoff = [DateTime]::UtcNow.AddHours(-24)
    $recent = @($Incidents | Where-Object {
        $at = [DateTime]::MinValue
        [DateTime]::TryParse([string]$_.detected, [ref]$at) -and $at.ToUniversalTime() -ge $cutoff -and $at.ToUniversalTime() -le [DateTime]::UtcNow
    } | Sort-Object detected -Descending | Select-Object -First 20)
    $subjects = @{ CustomerManagement = 'customermanagementapi'; VehicleManagement = 'vehiclemanagementapi'; WorkshopManagement = 'workshopmanagementapi' }
    foreach ($incident in $recent) {
        if ($incident.kind -notin @('Page unavailable', 'Container health failure', 'Latency regression')) { continue }
        $target = [string]$incident.subject
        if ($subjects.ContainsKey($target)) { $target = $subjects[$target] }
        if ($target -notin @($Dependencies.services)) { continue }
        $findings.Add([pscustomobject]@{ Type = 'Recorded incident'; Subject = $target; Summary = "$($incident.kind), last recorded state: $($incident.status). Historical evidence is not proof of a current failure."; Source = 'Monitor history (last 24 hours)' })
        foreach ($entry in @($Catalog | Where-Object target -eq $target)) {
            $priority[$entry.id] += $(if ($incident.kind -eq 'Latency regression' -and $entry.failureType -eq 'NetworkDelay') { 15 } else { 5 })
        }
    }
    foreach ($target in @('sqlserver', 'rabbitmq')) {
        $count = @($Dependencies.edges | Where-Object { $_.to -eq $target -or $_.from -eq $target }).Count
        if ($count -gt 1) {
            $findings.Add([pscustomobject]@{ Type = 'Potential risk'; Subject = $target; Summary = "$count mapped connections share this dependency. An outage could propagate; test evidence is required."; Source = 'Dependency map' })
            foreach ($entry in @($Catalog | Where-Object target -eq $target)) { $priority[$entry.id] += $count }
        }
    }
    $candidates = @($Catalog | ForEach-Object { [pscustomobject]@{ Id = $_.id; Priority = $priority[$_.id]; Target = $_.target; Reason = $_.reason } } | Sort-Object @{ Expression = 'Priority'; Descending = $true }, Id)
    return [pscustomobject]@{
        HealthyBaseline = [bool]$Baseline.Healthy; Findings = @($findings.ToArray()); Candidates = $candidates
        ProposedTests = @(
            @{ Name = 'Packet loss'; Executable = $false; Reason = 'Requires a bounded network-loss tool with verified cleanup.' },
            @{ Name = 'Database contention'; Executable = $false; Reason = 'Requires a dedicated test database, bounded workload and cancellation.' },
            @{ Name = 'Disk exhaustion'; Executable = $false; Reason = 'Requires a disposable size-limited volume; never fill the host or database volume.' }
        )
        Limitations = 'Read probes and recorded incidents cannot find every latent fault or establish root cause. Proposed tests are not executable. Only registered tools may be injected.'
    }
}
Export-ModuleMember -Function Get-FailureDiscovery
