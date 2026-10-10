using System.Net;
using System.Net.Http.Json;
using System.Text.Json.Nodes;
using Pitstop.ResilienceDashboard;
using Xunit;

namespace Dashboard.Tests;

public class DashboardIntegrationTests
{
    [Fact]
    public async Task Combined_checkout_detects_pause_scripts_and_reads_their_reports()
    {
        using var app = new TestApp(StubAiHandler.For());
        using var client = app.CreateClient();
        // Availability is file metadata only. Synthetic files must never execute.
        foreach (var script in new[] { "PauseExperiment.ps1", "pause-customer-api.ps1", "pause-vehicle-api.ps1" })
            await File.WriteAllTextAsync(Path.Combine(app.ScriptsDirectory, script), "throw 'must never execute'");

        var state = await client.GetFromJsonAsync<JsonNode>("/api/state");
        foreach (var item in state!["preparedExperiments"]!.AsArray())
        {
            Assert.True(item!["scriptAvailable"]!.GetValue<bool>());
            Assert.False(item["canExecute"]!.GetValue<bool>());
        }

        const string id = "20261011T020000000Z-c0ffee";
        var folder = Path.Combine(app.ScriptsDirectory, "results", id);
        Directory.CreateDirectory(folder);
        await File.WriteAllTextAsync(Path.Combine(folder, "report.json"),
            """{"RunId":"20261011T020000000Z-c0ffee","Experiment":"pause-customer-api","TargetService":"customermanagementapi","Restored":false,"Recovered":false,"Error":"synthetic rollback failure"}""");
        var report = await client.GetFromJsonAsync<JsonNode>("/api/runs/" + id);
        Assert.Equal("customermanagementapi", report!["TargetService"]!.GetValue<string>());
        Assert.False(report["Recovered"]!.GetValue<bool>());
        Assert.Equal("synthetic rollback failure", report["Error"]!.GetValue<string>());
        Assert.Empty(app.Runner.Invocations);
    }

    [Theory]
    [InlineData("20261011T001234Z", true)]
    [InlineData("20261011T001234Z-a1b2c3", true)]
    [InlineData("../secret", false)]
    [InlineData("run/secret", false)]
    [InlineData("run\\secret", false)]
    [InlineData("-run", false)]
    [InlineData("", false)]
    public void Report_ids_support_pause_suffixes_without_path_traversal(string id, bool valid) =>
        Assert.Equal(valid, ReportIds.IsValid(id));

    [Fact]
    public async Task Hyphenated_report_ids_reach_the_report_lookup()
    {
        using var app = new TestApp(StubAiHandler.For());
        using var client = app.CreateClient();
        var response = await client.GetAsync("/api/runs/nonexistent-pause-report");
        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
    }

    [Fact]
    public async Task Prepared_pause_experiments_are_visible_but_not_executable()
    {
        using var app = new TestApp(StubAiHandler.For());
        using var client = app.CreateClient();
        var state = await client.GetFromJsonAsync<JsonNode>("/api/state");
        var prepared = state!["preparedExperiments"]!.AsArray();
        Assert.Equal(2, prepared.Count);
        foreach (var item in prepared)
        {
            var name = item!["name"]!.GetValue<string>();
            Assert.False(item["canExecute"]!.GetValue<bool>());
            Assert.False(ExperimentCatalog.TryGet(name, out _));
            var preflight = await client.GetFromJsonAsync<JsonNode>("/api/preflight/" + name);
            Assert.False(preflight!["ok"]!.GetValue<bool>());
            var response = await client.PostAsJsonAsync("/api/experiments/run", new
            {
                experiment = name, durationSeconds = 15, approved = true, approvedBy = "integration test",
            });
            Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        }
        Assert.Empty(app.Runner.Invocations);
    }

    [Fact]
    public async Task Groq_only_installations_advertise_only_groq_mode()
    {
        using var app = new TestApp(StubAiHandler.For(), enableOllama: false);
        using var client = app.CreateClient();
        var state = await client.GetFromJsonAsync<JsonNode>("/api/ai/status");
        Assert.Equal("Groq", state!["mode"]!.GetValue<string>());
        Assert.Equal("Groq", Assert.Single(state["modes"]!.AsArray())!.GetValue<string>());
        Assert.DoesNotContain("localhost", app.Handler.CalledHosts);
    }

    [Theory]
    [InlineData("Auto")]
    [InlineData("Ollama")]
    public async Task Groq_only_installations_reject_other_provider_modes(string mode)
    {
        using var app = new TestApp(StubAiHandler.For(), enableOllama: false);
        using var client = app.CreateClient();
        var response = await client.PostAsJsonAsync("/api/ai/mode", new { mode });
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Empty(app.Handler.CalledHosts);
    }
    [Fact]
    public async Task Kill_switch_and_reports_use_the_isolated_runtime_directory()
    {
        using var app = new TestApp(StubAiHandler.For());
        using var client = app.CreateClient();
        var stop = Path.Combine(app.ScriptsDirectory, "STOP");
        var response = await client.PostAsync("/api/experiments/stop", null);
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.True(File.Exists(stop));
        var blocked = await client.PostAsJsonAsync("/api/experiments/run", new
        {
            experiment = "kill-service", durationSeconds = 25, approved = true,
        });
        Assert.Equal(HttpStatusCode.BadRequest, blocked.StatusCode);
        Assert.Empty(app.Runner.Invocations);

        const string id = "20261011T001234Z-a1b2c3";
        var folder = Path.Combine(app.ScriptsDirectory, "results", id);
        Directory.CreateDirectory(folder);
        await File.WriteAllTextAsync(Path.Combine(folder, "report.json"), System.Text.Json.JsonSerializer.Serialize(new { RunId = id, Experiment = "pause-customer-api" }));
        var report = await client.GetFromJsonAsync<JsonNode>("/api/runs/" + id);
        Assert.Equal("pause-customer-api", report!["Experiment"]!.GetValue<string>());
        var clear = await client.PostAsync("/api/experiments/clear-stop", null);
        Assert.Equal(HttpStatusCode.OK, clear.StatusCode);
        Assert.False(File.Exists(stop));
    }

}
