using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace Pitstop.ResilienceDashboard;

public sealed record EvidenceReference(string Reference, string Label, string? Value, bool Resolved);

/// <summary>Resolves model citations against exactly the evidence supplied to it.</summary>
public static class EvidenceReferenceResolver
{
    public static EvidenceReference Resolve(string reference, JsonNode evidence)
    {
        var path = reference.Trim();
        if (path.Length > 512 || !Regex.IsMatch(path, @"^[A-Za-z]\w*(?:\[\d+\]|\.[A-Za-z]\w*)*$"))
            return new(reference, "Narrative citation", reference, false);

        JsonNode? current = evidence;
        var labels = new List<string>();
        foreach (Match token in Regex.Matches(path, @"([A-Za-z]\w*)|\[(\d+)\]"))
        {
            if (token.Groups[2].Success)
            {
                if (current is not JsonArray array || !int.TryParse(token.Groups[2].Value, out var index)
                    || index >= array.Count)
                    return new(reference, "Unresolved evidence reference", null, false);
                current = array[index];
                if (current is JsonObject obj)
                {
                    var title = obj.FirstOrDefault(p =>
                        p.Key.Equals("Name", StringComparison.OrdinalIgnoreCase)
                        || p.Key.Equals("Title", StringComparison.OrdinalIgnoreCase)
                        || p.Key.Equals("Dimension", StringComparison.OrdinalIgnoreCase)).Value;
                    if (title is JsonValue name && name.TryGetValue<string>(out var text)) labels.Add(text);
                }
            }
            else
            {
                if (current is not JsonObject obj)
                    return new(reference, "Unresolved evidence reference", null, false);
                var key = token.Groups[1].Value;
                var match = obj.FirstOrDefault(p => p.Key.Equals(key, StringComparison.OrdinalIgnoreCase));
                if (match.Key is null)
                    return new(reference, "Unresolved evidence reference", null, false);
                current = match.Value;
                if (key.Equals("deterministicAnalysis", StringComparison.OrdinalIgnoreCase)) labels.Add("Measured assessment");
                else if (!key.Equals("dimensions", StringComparison.OrdinalIgnoreCase))
                    labels.Add(Regex.Replace(key, @"(?<=[a-z])([A-Z])", " $1"));
            }
        }
        var value = current?.ToJsonString() ?? "not measured";
        if (current is JsonValue scalar && scalar.TryGetValue<string>(out var str)) value = str;
        return new(reference, string.Join(" / ", labels), value, true);
    }
}
