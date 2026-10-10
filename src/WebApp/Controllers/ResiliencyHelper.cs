namespace PitStop.WebApp.Controllers;

public class ResiliencyHelper
{
    private Microsoft.Extensions.Logging.ILogger _logger;

    public ResiliencyHelper(Microsoft.Extensions.Logging.ILogger logger)
    {
        _logger = logger;
    }

    public async Task<IActionResult> ExecuteResilient(Func<Task<IActionResult>> action, IActionResult fallbackResult)
    {
        var fallbackPolicy = Policy<IActionResult>
            .Handle<Exception>()
            .FallbackAsync(
                fallbackResult,
                (e, c) => Task.Run(() => _logger.LogError($"Error occured during request-execution. Polly will fallback. Exception: {e.Exception.ToString()}")));

        return await fallbackPolicy
            .ExecuteAsync(action)
            .ConfigureAwait(false);
    }
}
