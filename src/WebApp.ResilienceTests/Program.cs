using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Logging.Abstractions;
using PitStop.WebApp.Controllers;

var helper = new ResiliencyHelper(NullLogger.Instance);
var fallback = new StatusCodeResult(503);
var attempts = 0;
var result = await helper.ExecuteResilient(() => {
    attempts++;
    throw new HttpRequestException("simulated failed write");
}, fallback);
if (attempts != 1 || !ReferenceEquals(result, fallback)) throw new Exception("Failed commands must not be replayed.");
var healthy = new OkResult();
if (!ReferenceEquals(await helper.ExecuteResilient(() => Task.FromResult<IActionResult>(healthy), fallback), healthy)) throw new Exception("Healthy response changed.");
attempts = 0;
result = await helper.ExecuteResilient(() => {
    attempts++;
    throw new TaskCanceledException("simulated dependency timeout");
}, fallback);
if (attempts != 1 || !ReferenceEquals(result, fallback)) throw new Exception("Timeout must fall back once.");
Console.WriteLine("PASS: healthy result, single write attempt, and timeout fallback.");
