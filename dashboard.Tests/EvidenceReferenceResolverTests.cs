using System.Text.Json.Nodes;
using Pitstop.ResilienceDashboard;
using Xunit;

namespace Dashboard.Tests;

public class EvidenceReferenceResolverTests
{
    private static readonly JsonNode Evidence = JsonNode.Parse("""
        {"deterministicAnalysis":{"Dimensions":[
          {"Name":"Containment","Earned":20},
          {"Name":"Graceful degradation","Earned":0}
        ]},"recovered":true,"recoverySeconds":null}
        """)!;

    [Fact]
    public void Dimension_citation_resolves_to_its_name_and_actual_value()
    {
        var resolved = EvidenceReferenceResolver.Resolve("DeterministicAnalysis.Dimensions[1].Earned", Evidence);
        Assert.True(resolved.Resolved);
        Assert.Equal("Measured assessment / Graceful degradation / Earned", resolved.Label);
        Assert.Equal("0", resolved.Value);
    }

    [Theory]
    [InlineData("DeterministicAnalysis.Dimensions[99].Earned")]
    [InlineData("unknown.field")]
    [InlineData("recovered;alert(1)")]
    public void Unsupported_paths_are_explicitly_unresolved(string path)
    {
        Assert.False(EvidenceReferenceResolver.Resolve(path, Evidence).Resolved);
    }

    [Fact]
    public void Null_measurements_are_never_presented_as_zero()
    {
        var resolved = EvidenceReferenceResolver.Resolve("recoverySeconds", Evidence);
        Assert.True(resolved.Resolved);
        Assert.Equal("not measured", resolved.Value);
    }
}
