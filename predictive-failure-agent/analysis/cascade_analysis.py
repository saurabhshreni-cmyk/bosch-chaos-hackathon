import networkx as nx


def cascade(graph, target):
    if target not in graph:
        raise ValueError("Target is not in the discovered service inventory")
    return [{"component": source, "path": list(reversed(nx.shortest_path(graph, source, target))), "impact": "Potential degradation through dependency chain; not proof of complete outage.", "dependency_kinds": [graph[a][b]["kinds"] for a, b in zip(nx.shortest_path(graph, source, target), nx.shortest_path(graph, source, target)[1:])]} for source in sorted(nx.ancestors(graph, target))]
