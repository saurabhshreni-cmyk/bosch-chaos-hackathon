namespace Pitstop.ResilienceDashboard;

internal static class ProviderConfiguration
{
    public static string? Validate(string endpoint, string model, int timeoutSeconds)
    {
        if (!Uri.TryCreate(endpoint, UriKind.Absolute, out var uri) ||
            (uri.Scheme != Uri.UriSchemeHttp && uri.Scheme != Uri.UriSchemeHttps) ||
            !string.IsNullOrEmpty(uri.UserInfo))
            return "Configure an absolute HTTP(S) endpoint without embedded credentials.";
        if (string.IsNullOrWhiteSpace(model)) return "Configure a non-empty model name.";
        // CancellationTokenSource.CancelAfter rejects intervals outside this range.
        if (timeoutSeconds <= 0 || (long)timeoutSeconds * 1000 > uint.MaxValue - 1L)
            return "Configure a positive timeout within the supported timer range.";
        return null;
    }
}
