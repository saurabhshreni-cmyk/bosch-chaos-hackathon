"""Generate reviewable inventory from real configuration, without runtime access."""
from pathlib import Path
from discovery.service_discovery import discover


def main():
    root = Path(__file__).resolve().parents[2]
    services, edges, warnings = discover(root)
    rows = ["# Discovered Pitstop service inventory", "", "Generated from this checkout by `python -m tools.export_inventory`. Configuration evidence only; not a live-state or recovery claim.", "", "| Service | Framework / role | Compose ports | Replicas | Limits | Restart | Health route |", "| --- | --- | --- | ---: | --- | --- | --- |"]
    for s in services:
        rows.append(f"| {s.name} | {s.framework} / {s.role} | {', '.join(s.ports) or 'not published'} | {s.replicas} | {str(s.limits) if s.limits else 'not configured'} | {s.restart} | {s.health_path or ('Compose check' if s.healthcheck else 'not discovered')} |")
    for s in services:
        rows.extend(["", f"## {s.name}", "", f"Runtime: {s.runtime}. Networks: {', '.join(s.networks)}.", "", f"Dockerfile: {s.dockerfile or 'image only'}. Build images: {', '.join(s.build_images) or 'not applicable'}.", "", "Environment names only: " + (", ".join(s.environment_names) or "none in Compose/Dockerfile") + ".", "", "Detected controls: " + ("; ".join(s.controls) or "none established by these checks") + ".", "", "Route attributes (may require controller-prefix composition): " + (", ".join(s.routes) or "none discovered") + ".", "", "Configured dependencies:"])
        unique = set()
        for edge in edges:
            key = (edge.target, edge.kind, edge.evidence.path, edge.evidence.line)
            if edge.source == s.name and key not in unique:
                rows.append(f"- {edge.target} ({edge.kind}, {edge.confidence}): `{edge.evidence.path}:{edge.evidence.line}`. {edge.detail}")
                unique.add(key)
        rows.extend(["", "Source locations:", *[f"- `{p}`" for p in s.code_paths if p.endswith(("Program.cs", "Worker.cs", ".csproj", "Dockerfile"))]])
    if warnings:
        rows.extend(["", "Discovery warnings:", *warnings])
    path = Path(__file__).resolve().parents[1] / "docs/service-inventory.md"
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"Exported {len(services)} services and {len(edges)} dependency records to docs/service-inventory.md")


if __name__ == "__main__":
    main()
