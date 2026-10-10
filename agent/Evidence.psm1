function Get-ProbeScore {
    param([Parameter(Mandatory)]$Report)
    $fault = @($Report.Samples | Where-Object Phase -eq 'fault')
    if (-not $fault.Count) { return [pscustomobject]@{ Value = $null; Method = 'No fault observations; score unavailable' } }
    $healthy = @($fault | Where-Object Healthy).Count / $fault.Count
    $withinBudget = 0
    foreach ($sample in $fault) {
        $baseline = @($Report.Samples | Where-Object { $_.Module -eq $sample.Module -and $_.Phase -eq 'baseline' -and $_.Healthy } | Sort-Object LatencyMs)
        if (-not $baseline.Count) { throw 'A healthy per-module baseline is required for scoring.' }
        $middle = [int][math]::Floor($baseline.Count / 2)
        $median = $baseline[$middle].LatencyMs
        if ($baseline.Count % 2 -eq 0) { $median = ($baseline[$middle-1].LatencyMs + $median) / 2 }
        if ($sample.Healthy -and $sample.LatencyMs -le [math]::Max($median * 3, $median + 250)) { $withinBudget++ }
    }
    $latency = $withinBudget / $fault.Count
    $recovery = 0
    if ($Report.Recovered -and $null -ne $Report.RecoverySeconds) { $recovery = [math]::Max([double]0, [double](1 - [double]$Report.RecoverySeconds / 120)) }
    [pscustomobject]@{
        Value = [math]::Round(50*$healthy + 20*$latency + 30*$recovery, 1)
        AvailabilityFraction = $healthy; HealthyWithinLatencyBudgetFraction = $latency; RecoveryComponent = $recovery
        Method = 'Read-probe score / 100 = 50*healthy fault fraction + 20*healthy within max(3*baseline median, median+250ms) fraction + 30*max(0,1-recovery seconds/120). Unverified recovery contributes zero.'
        Limitations = 'Heuristic for this experiment only; unequal sampling and censored timeouts. Not an AI score, calibrated SLA, write-correctness or durability guarantee.'
    }
}

function Get-Percentile95 {
    param([double[]]$Values)
    if (-not $Values.Count) { return $null }
    $sorted = @($Values | Sort-Object)
    return $sorted[[math]::Ceiling($sorted.Count * 0.95) - 1]
}

function Compare-ChaosReports {
    param([Parameter(Mandatory)]$Before, [Parameter(Mandatory)]$After)
    foreach ($field in @('TargetService','FailureType','DelayMilliseconds','RequestedDurationSeconds')) {
        if ($Before.$field -ne $After.$field) { throw "Comparison requires matching $field." }
    }
    if (-not $Before.Recovered -or -not $After.Recovered) { throw 'Both comparison experiments must recover.' }
    $rows = foreach ($module in @('CustomerManagement','VehicleManagement','WorkshopManagement')) {
        $left = @($Before.Samples | Where-Object { $_.Module -eq $module -and $_.Phase -eq 'fault' })
        $right = @($After.Samples | Where-Object { $_.Module -eq $module -and $_.Phase -eq 'fault' })
        $p1 = Get-Percentile95 -Values @($left.LatencyMs)
        $p2 = Get-Percentile95 -Values @($right.LatencyMs)
        [pscustomobject]@{ Module = $module; BeforeProbes = $left.Count; AfterProbes = $right.Count
            BeforeFailed = @($left | Where-Object { -not $_.Healthy }).Count; AfterFailed = @($right | Where-Object { -not $_.Healthy }).Count
            BeforeP95ObservedMs = $p1; AfterP95ObservedMs = $p2
            ObservedP95ReductionPercent = $(if ($p1 -gt 0 -and $null -ne $p2) { [math]::Round(100*(1-$p2/$p1),1) } else { $null })
        }
    }
    [pscustomobject]@{ BeforeRunId = $Before.RunId; AfterRunId = $After.RunId; ModuleComparison = @($rows)
        BeforeScore = Get-ProbeScore $Before; AfterScore = Get-ProbeScore $After
        Limitations = 'One matched before/after pair, not a causal statistical study. Timeout durations are lower bounds. Compare responsiveness, failure rate and sampling counts together; faster fallback is not restored availability.' }
}
Export-ModuleMember -Function Get-ProbeScore, Get-Percentile95, Compare-ChaosReports
