import networkx as nx


def build_graph(services, dependencies, runtime_only=True):
    """Direction: consumer -> dependency. Failure effects follow reverse edges."""
    graph = nx.DiGraph()
    graph.add_nodes_from(s.name for s in services)
    for edge in dependencies:
        if edge.source not in graph or edge.target not in graph:
            continue
        if runtime_only and edge.kind in {"startup", "logging"}:
            continue
        kinds = graph.get_edge_data(edge.source, edge.target, {}).get("kinds", [])
        graph.add_edge(edge.source, edge.target, kinds=sorted(set([*kinds, edge.kind])))
    return graph


def graph_metrics(graph):
    centrality = nx.betweenness_centrality(graph)
    # Path enumeration can be exponential. Count shortest dependency paths only.
    result = {}
    for node in graph:
        dependents = sorted(nx.ancestors(graph, node))
        result[node] = {"in_degree": graph.in_degree(node), "out_degree": graph.out_degree(node), "betweenness": centrality[node], "dependencies_reachable": len(nx.descendants(graph, node)), "affected_dependents": dependents, "dependent_count": len(dependents), "shortest_dependency_path_count": sum(nx.has_path(graph, source, node) for source in graph if source != node)}
    return result
