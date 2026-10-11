"""Local Streamlit UI; all analysis lives in the single backend agent."""
import os
import json
from datetime import datetime, timezone
import httpx
import networkx as nx
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="PFIA | Failure Intelligence", page_icon="P", layout="wide")
from dashboard.theme import apply_theme
apply_theme()

base = os.getenv("PFIA_BACKEND_URL", "http://127.0.0.1:8091").rstrip("/")
page = st.sidebar.radio("Platform page", ["PFIA Analysis", "Chaos Engineering", "Self-Healing", "Agent Collaboration", "Experiment History"])
if page != "PFIA Analysis":
    from dashboard.platform_ui import render
    render(base, page)
    st.stop()
st.title("Predictive Failure Intelligence")
st.caption("Read-only engineering evidence | Hypothetical scenarios | Analysis does not inject faults")


def api(path, payload=None):
    try:
        with httpx.Client(timeout=180, trust_env=False) as client:
            response = client.post(base + path, json=payload) if payload is not None else client.get(base + path)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError:
        st.error("PFIA backend unavailable or request rejected. Start the backend and check its local configuration.")
        return None


with st.sidebar:
    st.header("Analysis controls")
    runtime = st.checkbox("Collect read-only runtime evidence", value=False, help="Backend must enable runtime collection and specify the existing Compose project label.")
    use_groq = st.checkbox("Use Groq explanations", value=False, help="Requires PFIA_ENABLE_GROQ and a local API key. Sends compact findings, never source/configuration values.")
    if st.button("Analyze Application", type="primary", width="stretch"):
        with st.spinner("Discovering services and evaluating evidence..."):
            data = api("/api/analyze", {"runtime": runtime, "use_groq": use_groq})
            if data:
                st.session_state["analysis"] = data
    st.info("Scores indicate relative engineering risk. They are not probabilities or measured failure outcomes.")

if "analysis" not in st.session_state:
    data = api("/api/analysis")
    if data:
        st.session_state["analysis"] = data
    else:
        st.stop()
data = st.session_state["analysis"]
services = data["services"]
risks = data["weak_nodes"]
a, b, c, d = st.columns(4)
a.metric("Services discovered", len(services))
b.metric("Recorded findings", len(data["findings"]))
c.metric("Runtime containers sampled", len(data["metrics"]))
d.metric("Highest relative risk", f"{risks[0]['score']:.1f}/100" if risks else "Unknown")
st.caption("Last analysis: " + datetime.fromtimestamp(data["timestamp"], timezone.utc).isoformat())
for warning in data["warnings"]:
    st.warning(warning)

architecture, weakest, scenarios, findings, future, insights = st.tabs(["Architecture", "Weakest Nodes", "Failure Scenarios", "Resilience Findings", "Future Failure Analysis", "AI Insights"])
with architecture:
    st.subheader("Application architecture")
    st.caption("Arrows point from consumer to dependency. Startup and logging links appear here but do not imply business outage.")
    graph_focus = st.selectbox("Focus dependency graph", ["All services", *[s["name"] for s in services]])
    graph_layout = st.radio("Graph layout", ["Spring", "Circular"], horizontal=True)
    graph = nx.DiGraph()
    graph.add_nodes_from(s["name"] for s in services)
    graph.add_edges_from((e["source"], e["target"]) for e in data["dependencies"])
    if graph_focus != "All services":
        graph = graph.subgraph({graph_focus, *graph.predecessors(graph_focus), *graph.successors(graph_focus)}).copy()
    positions = nx.spring_layout(graph, seed=42) if graph_layout == "Spring" else nx.circular_layout(graph)
    figure = go.Figure()
    for source, target in graph.edges:
        x0, y0 = positions[source]
        x1, y1 = positions[target]
        figure.add_annotation(x=float(x1), y=float(y1), ax=float(x0), ay=float(y0), xref="x", yref="y", axref="x", ayref="y", showarrow=True, arrowhead=2, arrowwidth=1, arrowcolor="#405b7d", opacity=.6)
    scores = {r["component"]: r["score"] for r in risks}
    figure.add_trace(go.Scatter(x=[positions[n][0] for n in graph], y=[positions[n][1] for n in graph], mode="markers+text", text=list(graph), textposition="top center", hovertext=[f"{n}: relative risk {scores[n]}" for n in graph], hoverinfo="text", marker={"size": 20, "color": [scores[n] for n in graph], "colorscale": [[0, "#dbe8f6"], [.5, "#547faf"], [1, "#10294c"]], "cmin": 0, "cmax": 100, "showscale": True}))
    figure.update_layout(height=550, template="plotly_white", paper_bgcolor="#ffffff", plot_bgcolor="#ffffff", xaxis={"visible": False}, yaxis={"visible": False}, margin={"l": 10, "r": 10, "t": 20, "b": 10})
    st.plotly_chart(figure, width="stretch")
    st.dataframe([{k: s[k] for k in ("name", "role", "runtime", "ports", "replicas", "restart", "healthcheck")} for s in services], width="stretch")
    selected = st.selectbox("Service evidence", [s["name"] for s in services])
    st.json(next(s for s in services if s["name"] == selected))
    st.subheader("Runtime observations")
    if data["metrics"]:
        st.dataframe(data["metrics"], width="stretch")
        st.dataframe(data["health"], width="stretch")
    else:
        st.info("No runtime evidence collected. Container state alone would not prove business health.")
    retained = api("/api/metrics?limit=200")
    history = retained.get("history", []) if retained else []
    if history:
        observed = st.selectbox("Retained metric observations", sorted({row["component"] for row in history}))
        points = sorted([row for row in history if row["component"] == observed], key=lambda row: row["timestamp"])
        if len(points) >= 2:
            trend = go.Figure(go.Scatter(x=[datetime.fromtimestamp(row["timestamp"], timezone.utc) for row in points], y=[row["memory_bytes"] / 1048576 for row in points], mode="lines+markers", name="Observed memory MiB"))
            trend.update_layout(template="plotly_white", yaxis_title="Memory MiB", xaxis_title="Observed time (UTC)", height=260)
            st.plotly_chart(trend, width="stretch")
            st.caption("Retained observations only. Sparse samples do not establish a trend or future failure threshold.")
        else:
            st.info("Only one retained observation for this component; insufficient history for trends.")
    with st.expander("Dependency sources and confidence"):
        st.dataframe(data["dependencies"], width="stretch")
with weakest:
    st.subheader("Weakest components")
    min_risk = st.slider("Minimum relative risk", 0, 100, 0)
    visible_risks = [risk for risk in risks if risk["score"] >= min_risk]
    st.caption(f"Showing {len(visible_risks)} of {len(risks)} components")
    st.download_button("Download risk evidence (JSON)", data=json.dumps(visible_risks, indent=2), file_name="pfia-risk-evidence.json", mime="application/json")
    st.dataframe([{"rank": i+1, "component": r["component"], "relative_risk": r["score"], "scored_evidence_coverage": f"{r['evidence_coverage']:.0%}", "primary_concern": r["primary_concerns"][0] if r["primary_concerns"] else "See recorded factors", "potentially_affected_dependents": len(r["affected_dependents"])} for i, r in enumerate(visible_risks)], width="stretch")
    for risk in visible_risks:
        with st.expander(f"{risk['component']} | {risk['score']}/100"):
            st.write("Factors", risk["factors"])
            st.write("Missing evidence", risk["missing_evidence"])
            st.write("Potentially affected dependents", risk["affected_dependents"])
            st.write("Supporting evidence", risk["supporting_evidence"])
            st.write("Failure hypotheses", risk["failure_scenarios"])
            st.write("Suggested improvements", risk["mitigations"])
            st.write("Proposed verification", risk["proposed_verification"])
with scenarios:
    st.subheader("Evaluate a hypothetical incident")
    with st.form("scenario_form"):
        kind = st.selectbox("Scenario", ["traffic", "database", "broker", "network", "resource", "cascade", "container", "host"])
        target = st.selectbox("Target (use default for database/broker)", ["Default", *[s["name"] for s in services]])
        multiplier = st.select_slider("Traffic multiplier", options=[2, 5, 10])
        latency = st.slider("Additional dependency latency (ms)", 0, 10000, 100)
        loss = st.slider("Packet loss (%)", 0, 100, 0)
        if st.form_submit_button("Evaluate without injecting faults"):
            result = api("/api/scenarios/evaluate", {"kind": kind, "target": None if target == "Default" else target, "traffic_multiplier": multiplier, "latency_ms": latency, "packet_loss_percent": loss})
            if result:
                st.session_state["scenario_result"] = result
    if "scenario_result" in st.session_state:
        result = st.session_state["scenario_result"]
        st.info(result["detail"])
        st.write(result["assumptions"])
        st.dataframe(result["impacts"], width="stretch")
with findings:
    st.subheader("Configuration and source evidence")
    search = st.text_input("Search findings", placeholder="Service, issue or source path")
    severity = st.multiselect("Severity", ["high", "medium", "low"], default=["high", "medium", "low"])
    filtered_findings = [f for f in data["findings"] if f["severity"] in severity and search.casefold() in json.dumps(f).casefold()]
    st.caption(f"Showing {len(filtered_findings)} of {len(data['findings'])} findings")
    for finding in filtered_findings:
        with st.expander(f"{finding['severity'].upper()} | {finding['component']} | {finding['title']}"):
            st.caption(finding["status"])
            for evidence in finding["evidence"]:
                st.code(f"{evidence['path']}:{evidence['line']}", language=None)
                st.write(evidence["description"])
            st.write("Failure hypothesis: " + finding["scenario"])
            st.write("Suggested improvement: " + finding["mitigation"])
with future:
    st.subheader("Potential propagation and verification")
    for scenario in data["scenarios"]:
        with st.expander(scenario["kind"].capitalize()):
            st.write(scenario["detail"])
            st.write(scenario["assumptions"])
            st.dataframe(scenario["impacts"], width="stretch")
    st.subheader("Proposed controlled verification")
    st.caption("Recommendations do not grant approval. Use Chaos Engineering to review a separate proposal.")
    st.dataframe(data["recommendations"], width="stretch")
with insights:
    st.subheader("Groq explanations")
    st.warning("AI text is unverified hypothesis. Scores, measurements and dependency edges come from deterministic analysis.")
    if not data["ai_insights"]:
        st.info("Groq was not requested or is disabled. Deterministic analysis is available.")
    for response in data["ai_insights"]:
        st.write(response["status"])
        if response.get("narrative"):
            for item in response["narrative"]["hypotheses"]:
                with st.expander(item["component"]):
                    st.write(item)
            st.write("Missing evidence", response["narrative"]["missing_evidence"])
    usage = api("/api/llm-usage")
    if usage:
        st.write({k: v for k, v in usage.items() if k != "records"})
    st.write("Analysis limitations", data["limitations"])
