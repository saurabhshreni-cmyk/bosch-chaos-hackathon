using System.Net;
using System.Text.Json.Nodes;
using Pitstop.ResilienceDashboard;
using Xunit;

namespace Dashboard.Tests;

// Every HTTP request terminates in Handler. No test host, Docker or live provider.
public sealed class ProviderFailureFollowupTests : IDisposable
{
    private const string Key = "synthetic-configured-credential";
    private readonly string? previousKey = Environment.GetEnvironmentVariable("GROQ_API_KEY");
    public ProviderFailureFollowupTests() => Environment.SetEnvironmentVariable("GROQ_API_KEY", Key);
    public void Dispose() => Environment.SetEnvironmentVariable("GROQ_API_KEY", previousKey);

    private sealed class Handler(Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> respond) : HttpMessageHandler
    {
        public List<string> Paths { get; } = [];
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            Paths.Add(request.RequestUri!.AbsolutePath);
            return respond(request, ct);
        }
    }

    private static HttpResponseMessage Reply(string body, HttpStatusCode status = HttpStatusCode.OK) =>
        new(status) { Content = new StringContent(body) };
    private static readonly string Models = """{"models":[{"name":"qwen3.5:4b"}]}""";
    private static Handler Respond(string body, HttpStatusCode status = HttpStatusCode.OK) =>
        new((request, _) => Task.FromResult(request.RequestUri!.AbsolutePath.EndsWith("/api/tags")
            ? Reply(Models) : Reply(body, status)));
    private static AiProviderRouter Router(HttpClient http, AiOptions? options = null) =>
        new(new GroqClient(http, options ?? new()), new OllamaClient(http, options ?? new()),
            new AiModeStore(Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N"), "mode.json")));

    [Theory]
    [InlineData(0)]
    [InlineData(190)]
    public async Task Structured_error_redacts_configured_key_before_truncation(int prefixLength)
    {
        var body = new JsonObject { ["error"] = new JsonObject {
            ["message"] = new string('x', prefixLength) + " " + Key + " Authorization: Bearer alternate-synthetic-token" } };
        using var http = new HttpClient(Respond(body.ToJsonString(), HttpStatusCode.BadRequest));
        var result = await new GroqClient(http, new()).CompleteAsync("test", "test", "test", new JsonObject(), default);
        Assert.False(result.Ok);
        Assert.DoesNotContain(Key, result.Error);
        Assert.DoesNotContain("synthetic-configured", result.Error);
        Assert.DoesNotContain("alternate-synthetic-token", result.Error);
        Assert.DoesNotContain("Authorization: Bearer", result.Error);
    }

    [Theory]
    [InlineData("relative")]
    [InlineData("file:///synthetic")]
    [InlineData("https://user:synthetic-password@example.invalid")]
    public async Task Invalid_endpoints_fail_before_HTTP_without_echoing_configuration(string endpoint)
    {
        using var handler = Respond("{}");
        using var http = new HttpClient(handler);
        var options = new AiOptions { Groq = new() { Endpoint = endpoint }, Ollama = new() { BaseUrl = endpoint } };
        foreach (IAiProvider provider in new IAiProvider[] { new GroqClient(http, options), new OllamaClient(http, options) })
        {
            var result = await provider.CompleteAsync("test", "test", "test", new JsonObject(), default);
            Assert.False(result.Ok);
            Assert.Contains("configuration error", result.Error);
            Assert.DoesNotContain(endpoint, result.Error);
        }
        Assert.Empty(handler.Paths);
    }

    [Theory]
    [InlineData(0)]
    [InlineData(-1)]
    [InlineData(int.MaxValue)]
    public async Task Invalid_timeouts_fail_before_HTTP(int timeout)
    {
        using var handler = Respond("{}");
        using var http = new HttpClient(handler);
        var options = new AiOptions { Groq = new() { TimeoutSeconds = timeout }, Ollama = new() { TimeoutSeconds = timeout } };
        foreach (IAiProvider provider in new IAiProvider[] { new GroqClient(http, options), new OllamaClient(http, options) })
        {
            var result = await provider.CompleteAsync("test", "test", "test", new JsonObject(), default);
            Assert.False(result.Ok);
            Assert.Contains("timeout", result.Error);
        }
        Assert.Empty(handler.Paths);
    }

    [Fact]
    public async Task Empty_models_and_malformed_key_fail_before_HTTP()
    {
        using var handler = Respond("{}");
        using var http = new HttpClient(handler);
        var options = new AiOptions { Groq = new() { Model = " " }, Ollama = new() { Model = " " } };
        Assert.False((await new GroqClient(http, options).CompleteAsync("t", "t", "t", new JsonObject(), default)).Ok);
        Assert.False((await new OllamaClient(http, options).CompleteAsync("t", "t", "t", new JsonObject(), default)).Ok);
        Environment.SetEnvironmentVariable("GROQ_API_KEY", "synthetic invalid key");
        var result = await new GroqClient(http, new()).CompleteAsync("t", "t", "t", new JsonObject(), default);
        Assert.Contains("invalid whitespace", result.Error);
        Assert.DoesNotContain("synthetic invalid key", result.Error);
        Assert.Empty(handler.Paths);
    }

    [Fact]
    public async Task Precancelled_missing_key_does_not_become_provider_failure()
    {
        Environment.SetEnvironmentVariable("GROQ_API_KEY", null);
        using var handler = Respond("{}");
        using var http = new HttpClient(handler);
        using var cts = new CancellationTokenSource();
        cts.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() =>
            new GroqClient(http, new()).CompleteAsync("t", "t", "t", new JsonObject(), cts.Token));
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() =>
            Router(http).CompleteAsync<AiRecommendation>("t", "t", "t", AiPrompts.RecommendationSchema(), cts.Token));
        Assert.Empty(handler.Paths);
    }

    [Fact]
    public async Task Caller_cancellation_during_groq_does_not_trigger_fallback()
    {
        using var handler = new Handler(async (_, ct) => { await Task.Delay(Timeout.Infinite, ct); return Reply("{}"); });
        using var http = new HttpClient(handler);
        using var cts = new CancellationTokenSource(TimeSpan.FromMilliseconds(100));
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() =>
            Router(http).CompleteAsync<AiRecommendation>("t", "t", "t", AiPrompts.RecommendationSchema(), cts.Token));
        Assert.Single(handler.Paths);
        Assert.DoesNotContain("/api/tags", handler.Paths);
    }

    [Theory]
    [InlineData(HttpStatusCode.TooManyRequests)]
    [InlineData(HttpStatusCode.InternalServerError)]
    [InlineData(HttpStatusCode.BadRequest)]
    public async Task Eligible_HTTP_errors_fall_back_once(HttpStatusCode status)
    {
        using var handler = new Handler((request, _) => Task.FromResult(request.RequestUri!.Host == "api.groq.com"
            ? Reply("{}", status) : request.RequestUri.AbsolutePath.EndsWith("/api/tags")
                ? Reply(Models) : Reply(Envelope.Ollama(Envelope.Recommendation("kill-service", "workshopmanagementapi", 25)))));
        using var http = new HttpClient(handler);
        var result = await Router(http).CompleteAsync<AiRecommendation>("t", "t", "t", AiPrompts.RecommendationSchema(), default);
        Assert.True(result.Ok);
        Assert.Equal("ollama", result.Provider);
        Assert.Single(handler.Paths, p => p.EndsWith("/chat/completions"));
    }

    [Fact]
    public async Task Invalid_groq_configuration_can_fall_back_in_Auto()
    {
        using var handler = Respond(Envelope.Ollama(Envelope.Recommendation("kill-service", "workshopmanagementapi", 25)));
        using var http = new HttpClient(handler);
        var result = await Router(http, new AiOptions { Groq = new() { Endpoint = "relative" } })
            .CompleteAsync<AiRecommendation>("t", "t", "t", AiPrompts.RecommendationSchema(), default);
        Assert.True(result.Ok);
        Assert.Equal("ollama", result.Provider);
        Assert.DoesNotContain("/chat/completions", handler.Paths);
    }

    [Theory]
    [InlineData("{}")]
    [InlineData("{\"experiment\":\"arbitrary-shell\",\"durationSeconds\":25}")]
    public async Task Incomplete_or_unsafe_recommendations_are_rejected_without_fallback(string content)
    {
        using var handler = Respond(Envelope.Groq(content));
        using var http = new HttpClient(handler);
        var result = await Router(http).CompleteAsync<AiRecommendation>("t", "t", "t", AiPrompts.RecommendationSchema(), default);
        Assert.True(result.Ok); // Parsing success is distinct from safety validation.
        Assert.False(RecommendationValidator.Validate(result.Value).Allowed);
        Assert.Single(handler.Paths);
    }

    [Fact]
    public async Task Refused_connections_fail_both_providers_without_retry()
    {
        using var handler = new Handler((_, _) => throw new HttpRequestException("Authorization: Bearer " + Key));
        using var http = new HttpClient(handler);
        var result = await Router(http).CompleteAsync<AiRecommendation>("t", "t", "t", AiPrompts.RecommendationSchema(), default);
        Assert.False(result.Ok);
        Assert.Equal(2, handler.Paths.Count); // Groq completion then Ollama status.
        Assert.DoesNotContain(Key, result.Error);
        Assert.DoesNotContain("Authorization", result.Error);
    }
}
