namespace Pitstop.ResilienceDashboard;

// Display metadata only. Never consumed by validators or IExperimentRunner.
public static class PreparedExperiments
{
    public static object[] List(string scriptsDirectory) =>
    [
        Describe("pause-customer-api", "customermanagementapi", scriptsDirectory),
        Describe("pause-vehicle-api", "vehiclemanagementapi", scriptsDirectory),
    ];
    private static object Describe(string name, string target, string directory) => new
    {
        name, target,
        scriptAvailable = File.Exists(Path.Combine(directory, name + ".ps1"))
            && File.Exists(Path.Combine(directory, "PauseExperiment.ps1")),
        status = "Awaiting live cleanup verification",
        fault = "Pause container processes; test API timeouts and isolation.",
        recovery = "Detached watchdog unpauses the target; module-page recovery is measured.",
        defaultDuration = 15, maxDuration = 60, canExecute = false,
    };
}
public static class ReportIds
{
    public static bool IsValid(string? id) =>
        !string.IsNullOrEmpty(id) && id.Length <= 100 &&
        System.Text.RegularExpressions.Regex.IsMatch(id, @"\A[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*\z");
}
