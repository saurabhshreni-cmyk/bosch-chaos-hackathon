def detect(metrics):
    """Observed pressure flags, never inferred throughput or failure thresholds."""
    flags = []
    for metric in metrics:
        if metric.cpu_percent is not None and metric.cpu_percent >= 80:
            flags.append({"component": metric.component, "observation": "CPU usage >=80% of one core; not necessarily saturation", "value": metric.cpu_percent})
        if metric.configured_memory_limit and metric.memory_bytes / metric.configured_memory_limit >= .8:
            flags.append({"component": metric.component, "observation": "Memory usage >=80% of configured container limit", "value": metric.memory_bytes / metric.configured_memory_limit})
    return flags
